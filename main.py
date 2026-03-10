import os
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

SHUTDOWN="***!***"

text_que=Queue()
llm_que=Queue()
future_que=Queue()
tts_executor=ThreadPoolExecutor(max_workers=5)

async def async_speech_part(window):
    os.makedirs("log",exist_ok=True)
    logger=getLogger(log_name="main",log_path="log/speech.log")
    optimization_logger=getLogger(log_name="async_speech_part",log_path="log/optimization.log")

    load_dotenv("config/config.env")
    api_key = os.getenv("API_KEY")

    asr=async_speech.SenseVoiceController(log_name="asr",log_path="log/speech.log")
    llm_api=async_LLM_api(api_key=api_key,log_name="api",log_path="log/speech.log")
    tts=async_speech.GPT_SoVITSController("models/v2pp/mmk/tmp.json",log_name="tts",log_path="log/speech.log",inference_log_path="log/inference.log")
    ap=async_speech.AudioPlayer(log_name="audioplayer",log_path="log/speech.log")
    mm=RAG.MemoryManager(api_key,log_name="memory",log_path="log/memory.log")

    flags={
        "audioplayer_count":0,
        "audioplay_done":True,
        "session_id":0,
        "api_loop":None,
        "api_task":None,
        "last_audio_done":time()
    }

    for key,value in window.page_setting.config.items():flags[key]=value
    flags["api_key"]=api_key
    window.page_setting.config["api_key"]=api_key

    try:
        tasks = [
            llm_api.warmup(window.DOING),
            tts.start_service(window.DOING),
            asr.load_models(window.DOING),
            mm.load_prompt("SYSTEM_PROMPT.md")
        ]

        await asyncio.gather(*tasks)
        logger.info("✅ chat界面加载成功")
    except Exception as e:
        logger.error( f"❌ 初始化失败:{e}")
        tts_executor.shutdown(wait=False)
        window.clear_up.set()
        return
    
    window.prepare.set()

    def do_interpt():
        flags["session_id"]+=1
        if flags["api_task"] and flags["api_loop"]:
            try:
                flags["api_loop"].call_soon_threadsafe(flags["api_task"].cancel)
            except:
                pass
            logger.info("api任务被打断")
        ap.stop()
        flags["audioplay_done"]=True
        while not llm_que.empty(): 
            try: llm_que.get_nowait()
            except: break
        while not future_que.empty(): 
            try: future_que.get_nowait()
            except: break
        logger.info("打断完成")

    def _api_thread():
        loop=asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        flags["api_loop"] = loop

        async def run_api():
            while True:
                pii=await loop.run_in_executor(None,text_que.get)
                if pii==SHUTDOWN:
                    llm_que.put_nowait(SHUTDOWN)
                    break
                if pii==None: break
                session_id,content=pii
                if session_id!=flags["session_id"]:continue
                logger.info(f"✨:{content}")
                api_last=time()
                query_last=time()
                message=await mm.query(query=content)
                optimization_logger.info(f"记忆检索耗时:{time()-query_last:.2f}")

                flags["api_task"]=llm_api.start(
                    message=message,
                    model=SiliconCloud_model[flags["model_name"]]
                )

                try:
                    flag=True
                    llm_res=""
                    action=[]
                    llm_json=None
                    async for res_type,output in flags["api_task"]:
                        if session_id!=flags["session_id"]:
                            flags["api_task"].cancel()
                            flag=False
                            break
                        if res_type=="action":
                            action.append(output)
                            llm_res+=f"[{output}]"
                            continue
                        elif res_type=="json":
                            llm_json=output
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
                    flags["api_task"]=None
                    llm_que.put_nowait(None)
                    if flag: 
                        add_success=await mm.add_memory(content,llm_json)
                        if add_success:await mm.add_short_memory(content,llm_res)
            logger.info("llm线程结束")

        loop.run_until_complete(run_api())
        loop.close()

    def _stream_thread():
        loop=asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run_tts():
            while True:
                pii=await loop.run_in_executor(None,llm_que.get)
                if pii==SHUTDOWN:
                    future_que.put_nowait(SHUTDOWN)
                    break
                elif pii is None: 
                    future_que.put_nowait(None)
                    continue
                session_id,response=pii
                if session_id!=flags["session_id"] or response=="..." or response.strip()=="":continue

                def generate_tts_with_check(session_id,text):
                    if session_id!=flags["session_id"]:return None
                    return asyncio.run(tts.generate_tts(text, text_lang="auto"))

                future=tts_executor.submit(generate_tts_with_check,session_id,response)
                future_que.put_nowait((session_id,future))
            logger.info("tts线程结束")

        loop.run_until_complete(run_tts())
        loop.close()
        
    def _ap_thread():
        loop=asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run_ap():
            last=None
            while True:
                pii=await loop.run_in_executor(None,future_que.get) 
                if last is None:last=time()
                if pii==SHUTDOWN: break
                elif pii is None:
                    flags["audioplay_done"] = True
                    flags["last_audio_done"]=time()
                    continue
                session_id,future=pii
                if session_id!=flags["session_id"]: continue
                stream=future.result()
                if stream is None:continue
                if session_id!=flags["session_id"]: continue

                flags["audioplayer_count"]+=1
                optimization_logger.info(f"{flags['audioplayer_count']}次音频播放间隔{time()-last:.2f}")
                ap.set_volume(flags["volume"])
                await ap.play(stream)
                last=time()
        
        loop.run_until_complete(run_ap())
        loop.close()

    try:
        api_thread=Thread(target=_api_thread,daemon=False)
        stream_thread=Thread(target=_stream_thread,daemon=False)
        ap_thread=Thread(target=_ap_thread,daemon=False)
        api_thread.start()
        stream_thread.start()
        ap_thread.start()
        asr_last=time()
        interpts=[]

        while not window.DOING.is_set():
            for key,value in window.page_setting.config.items():
                if key=="api_key" and flags["api_key"]!=value:
                    logger.info("api_key改变")
                    window.hide()
                    text_que.put_nowait(None)
                    api_thread.join()
                    api_key=value
                    llm_api=async_LLM_api(api_key=api_key,log_name="api",log_path="log/speech.log")
                    await llm_api.warmup(window.DOING)
                    api_thread=Thread(target=_api_thread,daemon=False)
                    api_thread.start()
                    window.show()
                flags[key]=value

            if window.stackedWidget.currentIndex()==1:
                if window.page_chat.is_voice_mode:
                    window.page_chat.forbid_change.set()
                    asr_task=await asr.start(mode=flags["asr_mode"],window=window)
                    async for text in asr_task:
                        if asr_last:
                            optimization_logger.info(f"asr首次响应耗时{time()-asr_last:.2f}")
                            asr_last=None
                        if not flags["audioplay_done"]:print("当前对话还未结束，无法处理当前语音") 

                        if flags["audioplay_done"]:
                            if time()-flags["last_audio_done"] < flags["silence_threshold"]: continue
                            else: 
                                logger.info(text)
                                window.page_chat.chat_input.setPlainText(f"语音识别模式: {text}")
                            flags["session_id"]+=1
                            logger.info(f"会话{flags['session_id']}开始")
                            text_que.put_nowait((flags["session_id"],text))
                            flags["audioplay_done"]=False

                        elif any(word in text for word in interpts) or window.page_chat.interpt.is_set():
                            window.page_chat.interpt.clear()
                            do_interpt()
                        if flags["audioplay_done"]: window.page_chat.chat_input.setPlainText("语音识别模式(']'键退出): 准备就绪，请说话...")
                        await asyncio.sleep(0.5)

                    if asr.interpt: asr.interpt=False

                    while True:
                        if flags["audioplay_done"]  or window.page_chat.interpt.is_set():
                            window.page_chat.forbid_cahnge.clear()
                            break
                        else: await asyncio.sleep(1)
                else:
                    if window.page_chat.wait_for_get.is_set():
                        window.page_chat.forbid_change.set()
                        window.page_chat.wait_for_get.clear()
                        text=window.page_chat.text
                        flags["session_id"]+=1
                        logger.info(f"会话{flags['session_id']}开始")
                        text_que.put_nowait((flags["session_id"],text))
                        flags["audioplay_done"]=False
                    elif window.page_chat.interpt.is_set():
                        window.page_chat.interpt.clear()
                        do_interpt()
                        
                    else: await asyncio.sleep(2)

                    while True:
                        if  (flags["audioplay_done"] or window.page_chat.interpt.is_set()):
                            window.page_chat.forbid_change.clear()
                            break
                        else: await asyncio.sleep(1)
            else:await asyncio.sleep(2)
    finally:
        await mm.show_memories()
        logger.info("启动清理程序...")
        text_que.put_nowait(SHUTDOWN)
        tts_executor.shutdown(wait=False)
        kill()
        set_key("config/config.env", "API_KEY", api_key)
        logger.info("✅ 资源释放完成")
        window.clear_up.set()

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
    