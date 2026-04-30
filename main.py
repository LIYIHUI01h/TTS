import os
import json
import asyncio
from time import time
from queue import Queue
from UI import MyWindow
from qasync import QEventLoop
from datetime import datetime
from mika import async_speech,RAG
from mika.tool import getLogger,kill
from dotenv import load_dotenv,set_key
from PySide6.QtWidgets import QApplication
from mika.agent import ThinkAgentController,InteractionAgentController
from mika.websockets import  WebSocketController
from mika.scheduled_task import IdleController
from mika.api import async_LLM_api,SiliconCloud_model


SHUTDOWN="***!***"

text_que=asyncio.Queue()
llm_que=asyncio.Queue()
future_que=asyncio.Queue()

class GlobalVar:
    def __init__(self):
        self.main_done=asyncio.Event()
        self.audioplayer_count=0
        self.audioplay_done=asyncio.Event()
        self.session_id=0
        self.api_task=None
        self.asr_task=None
        self.last_audio_done=time()
        self.user_name="游客"
        self.tts_path="models/v2pp/mmk/tmp.json"
    def add_var(self,new_config):
        for key,value in new_config.items():
            setattr(self,key,value)

asr_load_done=False
flags=GlobalVar()
llm_interpt=asyncio.Event()
async def async_speech_part(window):
    start_last=time()
    os.makedirs("log",exist_ok=True)
    logger=getLogger(log_name="main",log_path="log/speech.log",mode='w')
    optimization_logger=getLogger(log_name="async_speech_part",log_path="log/optimization.log",mode='w')
    api_key=flags.api_key
    flags.audioplay_done.set()

    asr=async_speech.SenseVoiceController(log_name="asr",log_path="log/speech.log")
    # llm_api=async_LLM_api(api_key=api_key,log_name="llm",log_path="log/speech.log")
    # pic_llm=async_LLM_api(api_key=api_key,log_name="llm",log_path="log/speech.log",model=SiliconCloud_model["Qwen2-VL-72B"])
    tts=async_speech.GPT_SoVITSController(flags.tts_path,log_name="tts",log_path="log/speech.log",inference_log_path="log/inference.log")
    # tts=async_speech.QwenTTSController(flags.tts_path,log_name="tts",log_path="log/speech.log",inference_log_path="log/inference.log")
    ap=async_speech.AudioPlayer(log_name="audioplayer",log_path="log/speech.log")
    mm=RAG.MemoryManager(api_key,collection_name=flags.memory_name,log_name="memory",log_path="log/memory.log",model=flags.model_name,user_name=flags.user_name,agent_name=flags.name)
    ia=InteractionAgentController(api_key=api_key,memory_manager=mm,log_path="log/agent.log",log_name="interaction_agent")
    ta=ThinkAgentController(api_key=api_key,memory_manager=mm,text_que=text_que,flags=flags,log_path="log/agent.log",log_name="think_agent")
    # agent=AgentSkillsController(api_key=api_key,memory_manager=mm,log_name="agent",log_path="log/agent.log")
    ws = WebSocketController(host="127.0.0.1", port=8765,log_path="log/live2d.log",log_name="live2d")
    timer=IdleController(text_que,flags)
    window.page_memory.memory_manager=mm
    flags.ia=ia
    flags.ta=ta

    try:
        tasks = [
            ia.start(flags.prompt_path,window.DOING),
            ta.start(flags.prompt_path,window.DOING),
            tts.start_service(window.DOING),
        ]
        if flags.pattern=="live2d": tasks.append(window.page_chat.start_live2d_render())
        await asyncio.gather(*tasks)
        ws_task = asyncio.create_task(ws.start())
        logger.info("✅ chat界面加载成功")
        optimization_logger.info(f"启动耗时：{time()-start_last:.2f}")
        window.notify("chat界面加载成功")
    except Exception as e:
        logger.error( f"❌ 初始化失败:{e}")
        kill()
        window.clear_up.set()
        return
    
    window.prepare.set()

    async def do_interpt():
        flags.session_id+=1
        window.page_chat.forbid_change.clear()
        window.page_chat.update_ex_btn_style()
        window.page_chat.interpt.clear()
        while not llm_que.empty(): 
            try: llm_que.get_nowait()
            except: break
        while not future_que.empty(): 
            try: future_que.get_nowait() 
            except: break
            
        llm_interpt.set()
        ap.stop()
        flags.audioplay_done.set()

        asyncio.sleep(1)

    async def run_llm():
        while True:
            tri=await text_que.get()
            if tri==SHUTDOWN:
                llm_que.put_nowait(SHUTDOWN)
                break
            if tri==None: break
            session_id,content,images,call_back=tri
            if session_id!=flags.session_id:continue
            if not window.page_chat.forbid_change.is_set():
                window.page_chat.forbid_change.set()
                window.page_chat.update_ex_btn_style()
            logger.info(f"✨:{content}")
            query_last=time()

            message,json_data=await ia.quick_query(query=content,images=images,call_back=call_back)
            if not message:continue
            elif message=="OUTPUT_FORMAT_ERROR":
                llm_que.put_nowait((session_id,message,None))
                window.page_chat.add_chat_item(content=message,is_user=False)
                continue
            
            optimization_logger.info(f"message检索耗时:{time()-query_last:.2f}")

            api_last=time()
            if llm_interpt.is_set():llm_interpt.clear()

            if json_data:flags.api_task=ia.llm_api.start(message=message,interpt_event=llm_interpt,json_data=json_data)
            else:flags.api_task=ia.pic_llm.start(message=message,interpt_event=llm_interpt,json_data=json_data)

            try:
                flag=True
                llm_res=""
                action=Queue()
                llm_json=None
                async for res_type,output in flags.api_task:
                    if res_type=="interpt":
                        llm_interpt.clear()
                        raise
                        break
                    if res_type=="action":
                        action.put_nowait(output)
                        llm_res+=f"[{output}]"
                        continue
                    elif res_type=="json":
                        llm_json=output
                        logger.info(llm_json)
                        break
                    llm_res+=output
                    try:
                        act=action.get_nowait()
                    except:
                        act=None
                    llm_que.put_nowait((session_id,output,act))
                    if api_last:
                        optimization_logger.info(f"api首次响应耗时{time()-api_last:.2f}")
                        api_last=None
            except Exception as e:
                flag=False
                logger.info(f"api任务{session_id}被成功打断:{e}")
            finally:
                llm_que.put_nowait(None)
                if flag: 
                    date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")

                    if llm_json is None:llm_json={"text": llm_res,"mood_change": 0,"special_info": "picture_chat","callback": []}
                    elif "text" not in llm_json:
                        call_back.append({"output_format_error":llm_json})
                        text_que.put_nowait((flags.session_id,content,images,call_back))
                        continue
                    think_back=llm_json.get("think",[])
                    new_call_back=llm_json.get("callback",[])
                    if new_call_back: text_que.put_nowait((flags.session_id,"[__callback__]请根据工具调用结果，主动与用户聊天",[],new_call_back))
                    if think_back:asyncio.create_task(ta.query(think_list=think_back))
                    if not any(key=="think"  for dic in call_back for key in dic):await mm.add_short_memory(content,llm_res,date)
                    window.page_chat.add_chat_item(content=llm_json.get("text",""),is_user=False)
                    if not call_back and "[__callback__]" not in llm_json.get("text",[]):await mm.add_memory(content,llm_json,date,flags.user_name)
        logger.info("llm任务结束")

    async def run_tts():
        tts_semaphore = asyncio.Semaphore(5)
        while True:
            tri=await llm_que.get()
            if tri==SHUTDOWN:
                future_que.put_nowait(SHUTDOWN)
                break
            elif tri is None: 
                future_que.put_nowait(None)
                continue
            if timer.is_running:await timer.stop()
            session_id,response,act=tri
            if session_id!=flags.session_id or response=="..." or response.strip()=="":continue

            async def generate_tts_with_check(session_id,text):
                async with tts_semaphore:
                    if session_id != flags.session_id: return None
                    result = await tts.generate_tts(text, text_lang="auto")
                    if session_id != flags.session_id: return None
                    return result
 
            task=asyncio.create_task(generate_tts_with_check(session_id,response))
            future_que.put_nowait((session_id,task,act,response))
        logger.info("tts任务结束")
       
    async def run_ap():
        last=None
        while True:
            tri=await future_que.get()
            if last is None:last=time()
            if tri==SHUTDOWN: break
            elif tri is None:
                flags.audioplay_done.set()
                flags.last_audio_done=time()
                continue
            if timer.is_running:await timer.stop()
            session_id,future,act,text=tri
            if session_id != flags.session_id:
                future.cancel()
                continue
            if session_id!=flags.session_id: continue
            stream=await future
            if stream is None:continue
            if session_id!=flags.session_id: continue

            flags.audioplayer_count+=1
            ap.set_volume(flags.volume)
            if act:await ws.emit("expression",act)
            if text:await ws.emit("text",text)
            optimization_logger.info(f"{flags.audioplayer_count}次音频播放间隔{time()-last:.2f}")
            await ap.play(stream,ws=ws)
            if act:await ws.emit("expression",act)
            last=time()
        logger.info("audio_player任务结束")

    async def main_event_loop():
        asr_last=time()
        interpts=[""]
        nonlocal mm, ia, llm_task, memory_task, api_key
        while not window.DOING.is_set():
            mm.user_name=flags.user_name
            if flags.api_key!=api_key:
                window.hide()
                logger.info("api_key改变")
                text_que.put_nowait(None)
                llm_task.cancel()
                api_key=flags.api_key
                ia=InteractionAgentController(api_key=api_key,log_path="log/agent.log",log_name="interaction_agent")
                mm=RAG.MemoryManager(api_key,log_name="memory",log_path="log/memory.log",model=flags.model_name,collection_name=flags.memory_name)
                llm_task=asyncio.create_task(run_llm())
                memory_task=asyncio.create_task(mm.run_add_memory())
                window.show()

            if flags.name!=mm.agent_name:
                tasks=[mm.switch_memory(flags),ia.load_prompt(flags.prompt_path),ta.load_prompt(flags.prompt_path)]
                await asyncio.gather(*tasks)
                logger.info("✅ 智能体切换成功!!!")
            global asr_load_done
            if window.stackedWidget.currentIndex()==1:
                if window.page_chat.is_voice_mode:
                    if not window.page_chat.asr_prepare.is_set() and not asr_load_done: 
                        window.notify("语音识别模型加载中请稍等...")
                        asr_load_done = True
                        await asr.load_models(window.DOING)
                        window.notify("语音识别模型加载完成")
                        window.page_chat.asr_prepare.set()

                    if not flags.asr_task and flags.audioplay_done.is_set() and not window.page_chat.forbid_change.is_set():
                        logger.info("语音识别模式: 准备就绪，请说话...")
                        window.page_chat.chat_input.setPlainText("语音识别模式: 准备就绪，请说话...")
                        flags.asr_task = asyncio.create_task(asr.start(mode=flags.asr_mode, window=window))

                    if asr.wait_for_get.is_set():
                        if timer.is_running: await timer.stop()
                        asr.wait_for_get.clear() 
                        window.page_chat.forbid_change.set()
                        window.page_chat.update_ex_btn_style()
                        text = asr.text
                        asr.text = "" 
                        flags.session_id += 1
                        logger.info(f"会话 {flags.session_id} 开始: {text}")
                        window.page_chat.add_chat_item(text)
                        text_que.put_nowait((flags.session_id, text, [], []))
                        flags.audioplay_done.clear()
                        if flags.asr_task:
                            asr.stop()
                            flags.asr_task.cancel()
                            flags.asr_task = None

                    if window.page_chat.interpt.is_set():
                        await do_interpt()
                        if flags.asr_task:
                            asr.stop()
                            flags.asr_task.cancel()
                            flags.asr_task = None

                    if flags.audioplay_done.is_set():
                        if not timer.is_running: await timer.run()
                        window.page_chat.forbid_change.clear()
                        window.page_chat.update_ex_btn_style()
                    await asyncio.sleep(0.5)
                else:
                    if window.page_chat.wait_for_get.is_set():
                        if timer.is_running:await timer.stop()
                        window.page_chat.wait_for_get.clear()
                        window.page_chat.forbid_change.set()
                        window.page_chat.update_ex_btn_style()
                        text=window.page_chat.text
                        images = window.page_chat.current_images
                        flags.session_id+=1
                        logger.info(f"会话{flags.session_id}开始")
                        text_que.put_nowait((flags.session_id,text,images,[]))
                        flags.audioplay_done.clear()
                    elif window.page_chat.interpt.is_set():await do_interpt()
                    else: await asyncio.sleep(1)

                    if flags.audioplay_done.is_set():
                        if not timer.is_running: await timer.run()
                        window.page_chat.forbid_change.clear()
                        window.page_chat.update_ex_btn_style()
                    await asyncio.sleep(0.5)
            else:await asyncio.sleep(1)
        flags.main_done.set()
    try:
        llm_task=asyncio.create_task(run_llm())
        stream_task=asyncio.create_task(run_tts())
        ap_task=asyncio.create_task(run_ap())
        memory_task=asyncio.create_task(mm.run_add_memory())
        main_task=asyncio.create_task(main_event_loop())
        await flags.main_done.wait()
    finally:
        mm.new_memory_que.put_nowait(None)
        logger.info("启动清理程序...")
        text_que.put_nowait(SHUTDOWN)
        await mm.add_memory_done.wait()
        ws_task.cancel()
        timer.stop()
        # await mm.show_memories()
        kill()
        set_key("config/config.env", "API_KEY", api_key)
        logger.info("✅ 资源释放完成")
        window.clear_up.set()
        logger.info("开始释放UI资源...")

if __name__ == "__main__":
    app = QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = MyWindow(flags)
    window.show()

    loop.create_task(async_speech_part(window))
    try:
        with loop:loop.run_forever()
    finally:
        loop.close()
    