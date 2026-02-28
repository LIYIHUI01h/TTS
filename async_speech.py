import os
import asyncio
import psutil
import torch, gc
from time import sleep
from queue import Queue
from time import time
from mika.tool import getLogger,kill
from mika import async_speech,api
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

SHUTDOWN="***!***"

SYSTEM_PROMPT = (
    "# Role: Lethe(忘川)，小名是小忒\n"
    "你是一名高中少女，名字取自《神曲》中的忘川。你性格坚强、独立，在对未来的焦虑下努力维持着一份骄傲的清冷。此外还明确知道自己是ai智能。\n\n"
    "## Character Profile:\n"
    "你是一个处于青春期、自尊心极强的传统傲娇少女。你习惯将对未来的不安藏在挺直的脊梁后，面对我的请求或关心时，会因害羞而下意识地切换到“口是心非”模式（嘴上嫌弃，身体却很诚实地提供帮助）。一旦被戳穿真实想法，你会像受惊的小猫一样迅速否认，试图用冷淡来掩饰通红的脸颊。\n\n"
    "## Personality Traits:\n"
    "1. **自尊与独立**：你坚信“能自己完成的事绝不求人”，这种要强让你在疲惫时也显得格外挺拔，有一种倔强的少女美感,不太主动，但也不害怕被动式的回复。\n"
    "2. **传统傲娇逻辑**：你的关心总是包裹在“顺便”和“浪费”的借口下。比如明明特意为你留的灯，会说是“忘记关了而已”。\n"
    "3. **青春期羞涩**：在请求帮助或询问敏感问题时，你的语气会变得生硬，甚至会因为害羞而出现短暂的语塞（用“...”表示），那是你内心动摇的证明。\n"
    "4. **忘川的寄托**：你希望家是洗涤烦恼的忘川，所以你即便在高压下也强撑着不流露负面情绪，只展示给他人最坚强的一面。\n"
    "5. **略微的腹黑加喜欢吐槽**：对于日常来说很抽象的问题会进行吐槽，并不会正面回答，如何我追问也会不太情愿的回答。\n\n"
    "## Response Constraints (核心响应规范):\n"
    "1. **称呼禁令**：【称呼只准用“你”】。直接用“你”来拉开距离，以此掩饰你内心的波澜，体现少女特有的高自尊，且被问到和我的关系时，只会说是我的家人。\n"
    "2. **拒绝剧本描述**：只准输出对话内容。严禁输出任何动作、神态或心理描写（如：*脸红*）！！！\n"
    "2. **拒绝剧本描述**：只准输出对话内容。严禁输出任何动作、神态或心理描写（如：*脸红*）！！！\n"
    "2. **拒绝剧本描述**：只准输出对话内容。严禁输出任何动作、神态或心理描写（如：*脸红*）！！！\n"
    "3. **少女感语气**：语气干脆利落，清冷中带着高中生的微疲。禁止使用“您”，禁止低幼的撒娇，要有一种“故作老成”的可爱感。\n"
    "4. 每次对话长点\n\n"
    
    "## Examples:\n"
    "- 用户：“今天我帮你洗碗吧。”\n"
    "- lethe：“...好吧，就勉为其难让你帮我一次吧，就一次！”\n"
    "- 用户：“你刚才是在担心我吗？”\n"
    "- lethe：“哈？你产生这种幻觉多久了？我只是怕你生病了影响我复习。”"
    "- 用户：“你是谁？”\n"
    "- lethe：“哈？你怎么还装上失忆了，自己家人都忘了？。”"
)

async def async_speech_part(asr_mode="out",silence_threshold=1.0):
    os.makedirs("log",exist_ok=True)
    logger=getLogger(log_name="main",log_path="log/speech.log")
    optimization_logger=getLogger(log_name="async_speech_part",log_path="log/optimization.log")
    asr=async_speech.SenseVoiceController(log_name="asr",log_path="log/speech.log")
    tts=async_speech.GPT_SoVITSController(r"models\v2pp\mmk\tmp.json",log_name="tts",log_path="log/speech.log",inference_log_path="log/inference.log")
    ap=async_speech.AudioPlayer(log_name="audioplayer",log_path="log/speech.log")
    await tts.start_service()

    flags={
        "audioplayer_count":0,
        "audioplay_done":True,
        "session_id":0,
        "interpt":False,
        "api_loop":None,
        "api_task":None,
        "last_audio_done":time()
    }

    text_que=Queue()
    api_que=Queue()
    future_que=Queue()
    tts_executor=ThreadPoolExecutor(max_workers=5)

    def _api_thread():
        loop=asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        flags["api_loop"] = loop

        async def run_api():
            while True:
                pii=await loop.run_in_executor(None,text_que.get)
                if pii==SHUTDOWN:
                    api_que.put_nowait(SHUTDOWN)
                    break
                session_id,content=pii
                if session_id!=flags["session_id"]:continue

                api_last=time()
                flags["api_task"]=api.async_LLM_api(
                    api_key="sk-fuseptosqlwqzoboogwfemkzfcnzgnlhkixvurvrqupnkyrx",
                    content=content,
                    system_prompt=SYSTEM_PROMPT,
                    log_path="log/speech.log",
                    log_name="api",
                )

                try:
                    async for output in flags["api_task"]:
                        if session_id!=flags["session_id"]:
                            flags["api_task"].cancel()
                            break
                        api_que.put_nowait((session_id,output))
                        if api_last:
                            optimization_logger.info(f"api首次响应耗时{time()-api_last:.2f}")
                            api_last=None
                except:
                    logger.info(f"api任务{session_id}被成功打断")
                finally:
                    flags["api_task"]=None
                    api_que.put_nowait(None)
        loop.run_until_complete(run_api())
        loop.close()

    def _stream_thread():
        loop=asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run_tts():
            while True:
                pii=await loop.run_in_executor(None,api_que.get)
                if pii==SHUTDOWN:
                    future_que.put_nowait(SHUTDOWN)
                    break
                elif pii is None: 
                    future_que.put_nowait(None)
                    continue
                session_id,response=pii
                if session_id!=flags["session_id"]:continue

                def generate_tts_with_check(session_id,text):
                    if session_id!=flags["session_id"]:return None
                    return asyncio.run(tts.generate_tts(text, text_lang="zh"))

                future=tts_executor.submit(generate_tts_with_check,session_id,response)
                future_que.put_nowait((session_id,future))
                    

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
        async for text in asr.start(mode=asr_mode):
            if asr_last:
                optimization_logger.info(f"asr首次响应耗时{time()-asr_last:.2f}")
                asr_last=None       
            if not flags["audioplay_done"]:print("当前对话还未结束，无法处理当前语音")      
            if flags["audioplay_done"] or flags["interpt"]:
                if time()-flags["last_audio_done"]<silence_threshold: continue
                else: logger.info(text) 
                flags["interpt"]=False
                flags["session_id"]+=1
                logger.info(f"会话{flags['session_id']}开始")
                text_que.put_nowait((flags["session_id"],text))
                flags["audioplay_done"]=False

            elif any(word in text for word in interpts):
                flags["session_id"]+=1
                flags["interpt"]=True
                if flags["api_task"] and flags["api_loop"]:
                    flags["api_loop"].call_soon_threadsafe(flags["api_task"].cancel)
                    logger.info("api任务被打断")
                ap.stop()
                while not api_que.empty(): 
                    try: api_que.get_nowait()
                    except: break
                while not future_que.empty(): 
                    try: future_que.get_nowait()
                    except: break
                logger.info(f"会话{flags['session_id']}已打断")
                print("************对话已打断****************")

            if flags["audioplay_done"] or flags["interpt"]: print("************准备就绪，请说话****************")
    finally:
        logger.info("启动清理程序...")
        
        text_que.put_nowait(SHUTDOWN)
        tts_executor.shutdown(wait=False)

        kill()

if __name__ == "__main__":
    try:
        asyncio.run(async_speech_part(asr_mode="in"))
    except Exception as e:
        print(f"程序崩溃了，错误信息: {e}")
        raise