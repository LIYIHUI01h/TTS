import base64
import io
import mss
import ctypes
import asyncio
import win32gui
import pyautogui
import ctypes.wintypes
from PIL import Image
import win32process
from mika.api import * 
from mika.tool import getLogger
from ddgs import DDGS

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

class AgentSkillsController:
    def __init__(self,api_key,memory_manager=None,log_path="log/agent.log",log_name="agent"):
        self.mm=memory_manager
        self.weather_client = httpx.AsyncClient(timeout=10.0, trust_env=False)
        self.logger=getLogger(log_path=log_path,log_name=log_name,mode='w',stream=False)
        self.small_api_llm=async_LLM_api(api_key=api_key,log_path=log_path,log_name="agent_llm",model=SiliconCloud_model["Qwen2.5-7B"])
        self.api_embedding = async_embedding_api(api_key=api_key)
    async def query_dispatch(self, query):
        history_lines = []
        for ques, res,date in list(self.mm.short_memory_que._queue):
            history_lines.append(f"[{date}] {self.mm.user_name}: {ques};{self.mm.agent_name}: {res}")
        context_str = "\n---\n".join(history_lines)

        system_prompt = """
            你是一个 AI 助手的中控调度员。请分析用户的输入，决定是否需要启动以下增强功能。
            【判断准则】：
            1. memory:  - 若涉及对过往事实、过往偏好、过去约定等的追溯(即需要进行回忆时)，则为 true。
                        - 纯即时社交辞令、无需背景、即时话题的通用回答为 false。
            2. weather: 明确询问当地天气、穿衣建议、出行环境时为 true。
            3. search (list): 
               - 如果涉及百科知识、事实核查、人物/番剧详情、最新资讯等，返回 2-3 个精准的搜索关键词数组。
               - 如果不需要搜索或没有关键词，返回空数组 []
            4. digital_vision: 需要使用视觉观看用户的屏幕内容，即用户需要你看屏幕时为true
            5. physical_vision: 需要调用摄像查看用户标签，或用户需要你看摄像头时为true
            -- 若只知道需要使用视觉，但无法区分时查看摄像头还是屏幕，则默认屏幕，绝大部分情况，两个视觉只取一个。

            【输出格式】：
            严格返回 JSON：{"search": ["关键词1", "关键词2"], "weather": bool,"digital_vision":bool,"physical_vision":bool,"memory": bool}
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{query}"},
        ]

        try:
            cnt=0
            while True:
                cnt+=1
                dispatch_plan = await self.small_api_llm.start_nostream_json(messages)
                self.logger.info(f"🎯 调度决策: {dispatch_plan}")
                if len(dispatch_plan)==5 or cnt>3 :break
                self.logger.info(f"🎯 调度决策出错，正在重试")
                messages.append( {"role": "system", "content": f"{dispatch_plan}这是你上一轮的分析，不符合要求，请重试"})
                messages.append({"role": "user", "content": f"{query}"})
            if cnt>3:return {"search": [], "weather": False,"digital_vision":False,"physical_vision":False,"memory": False}
            if isinstance(dispatch_plan, dict): return dispatch_plan
            return {"search": [], "weather": False,"digital_vision":False,"physical_vision":False,"memory": False}
            
        except Exception as e:
            self.logger.error(f"❌ 调度器查询失败: {e}")
            return {"search": [], "weather": False,"digital_vision":False,"physical_vision":False,"memory": False}

    async def query(self,query,images=[],is_search=False):
        user_query=True
        if "【idle lock】" in query:
            query=query[11:]
            user_query=False

        if not is_search:dispatch=await self.query_dispatch(query)
        else: dispatch={"search": [], "weather": False,"digital_vision":False,"physical_vision":False,"memory": False}
        current_time_info = f"\n当前时间：[{datetime.now().strftime('%Y-%m-%d %H:%M:%S %A')}]"

        if images or dispatch["digital_vision"] or dispatch["physical_vision"] :message=[{"role":"system","content":self.mm.VL_SYSTEM_PROMPT+current_time_info}]
        else:message=[{"role":"system","content":self.mm.SYSTEM_PROMPT+current_time_info}]

        tasks=[]
        json_data=(len(images)==0)

        for disp,value in dispatch.items():
            if disp=="memory": tasks.append(self.mm.query(query,images=images,do_query_split=value,is_search=is_search,user_query=user_query))
            elif disp=="weather" and value: tasks.append(self.weather_skill(query))
            elif disp=="digital_vision" and value:
                tasks.append(self.digital_vision_skill())
                json_data=False
            elif disp=="physical_vision" and value:
                tasks.append(self.physical_vision_skill())
                json_data=False
            # elif disp=="search" and len(value)>0: tasks.append(self.search_skill(value,is_search=is_search))

        messages=await asyncio.gather(*tasks)
        for mess in messages:
            message.extend(mess)
        return message,json_data

    async def weather_skill(self, query=None):
        url = "https://wttr.in/?format=j1&lang=zh"
        try:
            resp = await self.weather_client.get(url)
            if resp.status_code != 200:
                self.logger.error(f"weatherskill: wttr.in 返回状态码 {resp.status_code}")
                return []
            data = resp.json()

            area = data['nearest_area'][0]['areaName'][0]['value']
            region = data['nearest_area'][0]['region'][0]['value']

            curr = data['current_condition'][0]
            curr_temp = curr['temp_C']
            curr_desc = curr['lang_zh'][0]['value']
            humidity = curr['humidity']

            tomorrow = data['weather'][1]
            t_date = tomorrow['date']
            t_max = tomorrow['maxtempC']
            t_min = tomorrow['mintempC']
            t_desc = tomorrow['hourly'][4]['lang_zh'][0]['value']

            weather_context = f"""
                ### [实时环境感知数据]
                当前定位：中国 {region} {area}
                【今日实时】{curr_desc}，气温 {curr_temp}°C，湿度 {humidity}%，风速 {curr['windspeedKmph']}km/h
                【明日预报】({t_date})：{t_desc}，气温区间 {t_min}°C ~ {t_max}°C
                你暂时只支持本地天气查询，如果用户让你查询别处的天气，告诉他你的功能暂时只支持本地天气查询
                --- 
            """

            self.logger.info(f"本地天气查询结果：{weather_context}")
            return [{"role": "system", "content": weather_context}]

        except Exception as e:
            self.logger.error(f"⚠️ Weather Skill 运行异常: {e}")
            return [{"role": "system", "content": "天气查询功能异常"}]
        
    async def search_skill(self, keywords_list,is_search=False):
        if not keywords_list: return []

        async def fetch_one(word):
            max_results = 5
            safe_word = f"{word} 百科 资讯" 
            black_list = [
                "91", "探花", "啪啪", "吃瓜", "乱伦", "海角", "成人", "色情", "视频在线", 
                "中出", "无套", "情趣", "极品女生", "爆料", "开盒", "性爱", "母子", "黑帮",
                "女郎", "泡泡浴", "淫", "欲", "MEYD", "JUFE", "ABP"
            ]

            try:
                def sync_search():
                    with DDGS(proxy=None, timeout=10) as ddgs:
                        return list(ddgs.text(safe_word, max_results=max_results))

                results = await asyncio.to_thread(sync_search)

                if not results:
                    return f"🔍 关于 '{word}' 的搜索：未找到相关结果。"

                formatted_results = []
                for r in results:
                    title = r.get('title', '无标题')
                    body = r.get('body', '无摘要')
                    
                    content_to_check = (title + body).lower()
                    if any(bad_word.lower() in content_to_check for bad_word in black_list):
                        continue

                    formatted_results.append(f"【{title}】: {body}")

                if not formatted_results:
                    return f"🔍 关于 '{word}' 的搜索内容已被安全策略过滤。"

                final_text = "\n".join([f"{i+1}. {text}" for i, text in enumerate(formatted_results)])
                return f"--- 关键词 '{word}' 的搜索结果 ---\n{final_text}"

            except Exception as e:
                self.logger.error(f"❌ 搜索词 '{word}' 失败: {e}")
                return f"⚠️ 搜索词 '{word}' 时发生错误。"

        try:
            self.logger.info(f"🔎 正在联网搜索：{keywords_list}")
            search_tasks = [fetch_one(w) for w in keywords_list]
            all_content = await asyncio.gather(*search_tasks)
            self.logger.info("搜索任务完成")
            search_context = "\n\n".join(all_content)
            
            final_system_message = f"""
                ### [互联网实时搜索结果]
                # 以下是根据用户提问在网上检索到的信息：{search_context}
                # 搜索结果只保存这一轮，请结合搜索结果回答，防止查询结果浪费---
            """
            self.logger.info(f"联网查询结果：{final_system_message}")
            if not is_search:return [{"role": "system", "content": final_system_message}]
            else: return final_system_message

        except Exception as e:
            self.logger.error(f"⚠️ Search Skill 运行异常: {e}")
            return [{"role": "system", "content": "联网查询功能异常"}]

    def _get_target_area(self):
        x, y = pyautogui.position()
        hwnd = win32gui.WindowFromPoint((x, y))
        
        while win32gui.GetParent(hwnd):
            hwnd = win32gui.GetParent(hwnd)

        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        
        invalid_classes = ["Progman", "WorkerW", "Shell_TrayWnd", "NotifyIconOverflowWindow"]
        
        if title and class_name not in invalid_classes:
            rect = win32gui.GetWindowRect(hwnd)
            area = {
                "left": rect[0], "top": rect[1],
                "width": rect[2] - rect[0], "height": rect[3] - rect[1]
            }
            return area, f"Window: {title}"
        else:
            with mss.mss() as sct:
                for m in sct.monitors[1:]:
                    if (m["left"] <= x < m["left"] + m["width"] and
                        m["top"] <= y < m["top"] + m["height"]):
                        return m, "Full Screen"
                return sct.monitors[1], "Primary Screen"

    async def digital_vision_skill(self):
        try:
            loop = asyncio.get_event_loop()
            area, source_name = await loop.run_in_executor(None, self._get_target_area)

            def _capture_and_encode():
                with mss.mss() as sct:
                    sct_img = sct.grab(area)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    
                    if img.width > 1600 or img.height > 1600:
                        img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                    
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=85)
                    
                    return base64.b64encode(buffer.getvalue()).decode()
            img_base64 = await loop.run_in_executor(None, _capture_and_encode)
            return [{
                "role": "user", 
                "content": [
                    {
                        "type": "text", 
                        "text": f"已经截取了鼠标指向的实时屏幕画面：{source_name}。请根据此图回答用户问题。"
                    },
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    }
                ]
            }]

        except Exception as e:
            self.logger(f"❌ 截屏失败: {e}")
            return []

    async def physical_vision_skill(self):
        pass