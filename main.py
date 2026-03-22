import os
from datetime import datetime
import asyncio
from dotenv import load_dotenv,set_key
from UI.UI import MyWindow
from queue import Queue
from time import time
from PySide6.QtWidgets import QApplication
from mika.tool import getLogger,kill
from mika import async_speech,RAG
from mika.api import async_LLM_api,SiliconCloud_model
from qasync import QEventLoop
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-gpu --num-raster-threads=4"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

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
        self.last_audio_done=time()
        self.user_name="游客"
        self.agent_name="浅宜"
    def add_var(self,new_config):
        for key,value in new_config.items():
            setattr(self,key,value)

async def async_speech_part(window):
    os.makedirs("log",exist_ok=True)
    logger=getLogger(log_name="main",log_path="log/speech.log")
    optimization_logger=getLogger(log_name="async_speech_part",log_path="log/optimization.log")

    load_dotenv("config/config.env")
    api_key = os.getenv("API_KEY")

    flags=GlobalVar()
    flags.audioplay_done.set()
    flags.add_var(window.page_setting.config)
    flags.add_var({"api_key":api_key,"model_name":flags.model_name})
    window.page_setting.config["api_key"]=api_key
    window.page_chat.audioplay_done=flags.audioplay_done

    asr=async_speech.SenseVoiceController(log_name="asr",log_path="log/speech.log")
    llm_api=async_LLM_api(api_key=api_key,log_name="llm",log_path="log/speech.log")
    tts=async_speech.GPT_SoVITSController("models/v2pp/mmk/tmp.json",log_name="tts",log_path="log/speech.log",inference_log_path="log/inference.log")
    ap=async_speech.AudioPlayer(log_name="audioplayer",log_path="log/speech.log")
    mm=RAG.MemoryManager(api_key,log_name="memory",log_path="log/memory.log",model=flags.model_name,user_name=flags.user_name)
    window.page_memory.memory_manager=mm

    try:
        tasks = [
            llm_api.warmup(window.DOING),
            mm.api_llm.warmup(window.DOING),
            tts.start_service(window.DOING),
            mm.load_prompt("SYSTEM_PROMPT.md",include_core_memory=False)
        ]

        await asyncio.gather(*tasks)
        logger.info("✅ chat界面加载成功")
        window.notify("chat界面加载成功")
    except Exception as e:
        logger.error( f"❌ 初始化失败:{e}")
        kill()
        window.clear_up.set()
        return
    
    window.prepare.set()

    async def do_interpt():
        flags.session_id+=1
        window.page_chat.interpt.set()
        ap.stop()
        flags.audioplay_done.set()
        while not llm_que.empty(): 
            try: llm_que.get_nowait()
            except: break
        while not future_que.empty(): 
            try: future_que.get_nowait()
            except: break
        asyncio.sleep(1)

    async def run_llm():
        while True:
            tri=await text_que.get()
            if tri==SHUTDOWN:
                llm_que.put_nowait(SHUTDOWN)
                break
            if tri==None: break
            session_id,content,images=tri
            if session_id!=flags.session_id:continue
            logger.info(f"✨:{content}")
            api_last=time()
            query_last=time()
            message=await mm.query(query=content,images=images)
            optimization_logger.info(f"记忆检索耗时:{time()-query_last:.2f}")

            flags.api_task=llm_api.start( message=message,model=flags.model_name,interpt_event=window.page_chat.interpt)

            try:
                flag=True
                llm_res=""
                action=[]
                llm_json=None
                async for res_type,output in flags.api_task:
                    if res_type=="interpt":
                        window.page_chat.interpt.clear()
                        raise
                        break
                    if res_type=="action":
                        action.append(output)
                        llm_res+=f"[{output}]"
                        continue
                    elif res_type=="json":
                        llm_json=output
                        logger.info(llm_json)
                        break
                    llm_res+=output
                    llm_que.put_nowait((session_id,output))
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
                    await mm.add_memory(content,llm_json,date,flags.user_name)
                    await mm.add_short_memory(content,llm_res,date)
        logger.info("llm任务结束")

    async def run_tts():
        tts_semaphore = asyncio.Semaphore(5)
        while True:
            pii=await llm_que.get()
            if pii==SHUTDOWN:
                future_que.put_nowait(SHUTDOWN)
                break
            elif pii is None: 
                future_que.put_nowait(None)
                continue
            session_id,response=pii
            if session_id!=flags.session_id or response=="..." or response.strip()=="":continue

            async def generate_tts_with_check(session_id,text):
                async with tts_semaphore:
                    if session_id != flags.session_id: return None
                    result = await tts.generate_tts(text, text_lang="auto")
                    if session_id != flags.session_id: return None
                    return result
 
            task=asyncio.create_task(generate_tts_with_check(session_id,response))
            future_que.put_nowait((session_id,task))
        logger.info("tts任务结束")
       
    async def run_ap():
        last=None
        while True:
            pii=await future_que.get()
            if last is None:last=time()
            if pii==SHUTDOWN: break
            elif pii is None:
                flags.audioplay_done.set()
                flags.last_audio_done=time()
                continue
            session_id,future=pii
            if session_id != flags.session_id:
                future.cancel()
                continue
            if session_id!=flags.session_id: continue
            stream=await future
            if stream is None:continue
            if session_id!=flags.session_id: continue

            flags.audioplayer_count+=1
            optimization_logger.info(f"{flags.audioplayer_count}次音频播放间隔{time()-last:.2f}")
            ap.set_volume(flags.volume)
            await ap.play(stream)
            last=time()
        logger.info("audio_player任务结束")

    async def main_event_loop():
        asr_last=time()
        interpts=[]
        while not window.DOING.is_set():
            nonlocal mm, llm_api, llm_task, memory_task, api_key

            if window.page_home.user_name!=flags.user_name:
                flags.user_name= window.page_home.user_name
                mm.user_name=flags.user_name
            for key,value in window.page_setting.config.items():
                if key=="api_key" and flags.api_key!=value:
                    window.hide()
                    logger.info("api_key改变")
                    text_que.put_nowait(None)
                    llm_task.cancel()
                    api_key=value
                    llm_api=async_LLM_api(api_key=api_key,log_name="llm",log_path="log/speech.log")
                    mm=RAG.MemoryManager(api_key,log_name="memory",log_path="log/memory.log",model=flags.model_name)
                    await llm_api.warmup(window.DOING)
                    await mm.api_llm.warmup(window.DOING)
                    llm_task=asyncio.create_task(run_llm())
                    memory_task=asyncio.create_task(mm.run_add_memory())
                    window.show()
                setattr(flags,key,value)

            if window.stackedWidget.currentIndex()==1:
                if window.page_chat.is_voice_mode:
                    if not window.page_chat.asr_prepare.is_set(): 
                        window.notify("语音识别模型加载中请稍等...")
                        await asr.load_models(window.DOING),
                        window.notify("语音识别模型加载完成")
                        window.page_chat.asr_prepare.set()
                    window.page_chat.forbid_change.set()
                    window.page_chat.update_ex_btn_style()
                    asr_task=await asr.start(mode=flags.asr_mode,window=window)
                    async for text in asr_task:
                        if asr_last:
                            optimization_logger.info(f"asr首次响应耗时{time()-asr_last:.2f}")
                            asr_last=None
                        if not flags.audioplay_done.is_set():print("当前对话还未结束，无法处理当前语音")

                        if flags.audioplay_done.is_set():
                            if time()-flags.last_audio_done < flags.silence_threshold: continue
                            else: 
                                logger.info(text)
                            flags.session_id+=1
                            logger.info(f"会话{flags.session_id}开始")
                            text_que.put_nowait((flags.session_id,text,[]))
                            flags.audioplay_done.clear()

                        elif any(word in text for word in interpts):await do_interpt()
                        if flags.audioplay_done.is_set: window.page_chat.chat_input.setPlainText("语音识别模式(']'键退出): 准备就绪，请说话...")

                    if asr.interpt: asr.interpt=False

                    if flags.audioplay_done.is_set():
                        window.page_chat.forbid_change.clear()
                        window.page_chat.update_ex_btn_style()
                    await asyncio.sleep(0.5)
                else:
                    if window.page_chat.wait_for_get.is_set():
                        window.page_chat.wait_for_get.clear()
                        window.page_chat.forbid_change.set()
                        window.page_chat.update_ex_btn_style()
                        text=window.page_chat.text
                        images = window.page_chat.current_images
                        flags.session_id+=1
                        logger.info(f"会话{flags.session_id}开始")
                        text_que.put_nowait((flags.session_id,text,images))
                        flags.audioplay_done.clear()
                    elif window.page_chat.interpt.is_set():await do_interpt()
                    else: await asyncio.sleep(2)

                    if flags.audioplay_done.is_set():
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
        await mm.show_memories()
        kill()
        set_key("config/config.env", "API_KEY", api_key)
        logger.info("✅ 资源释放完成")
        window.clear_up.set()
        logger.info("开始释放UI资源...")

if __name__ == "__main__":
    app = QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = MyWindow()
    window.show()

    loop.create_task(async_speech_part(window))
    try:
        with loop:loop.run_forever()
    finally:
        loop.close()
    