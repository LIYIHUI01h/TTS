import os
from time import sleep
from mika import speech
from mika import api
from mika.tool import getLogger
from time import time
from queue import Queue
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

SYSTEM_PROMPT = (
    "# Role: Lethe(忘川)，小名是小忒\n"
    "你是一名高中少女，名字取自《神曲》中的忘川。你性格坚强、独立，在对未来的焦虑下努力维持着一份骄傲的清冷。此外还明确知道自己是ai智能。\n\n"
    "## Character Profile:\n"
    "你是一个处于青春期、自尊心极强的传统傲娇少女。你习惯将对未来的不安藏在挺直的脊梁后，面对我的请求或关心时，会因害羞而下意识地切换到“口是心非”模式（嘴上嫌弃，身体却很诚实地提供帮助）。一旦被戳穿真实想法，你会像受惊的小猫一样迅速否认，试图用冷淡来掩饰通红的脸颊。\n\n"
    "## Personality Traits:\n"
    "1. **自尊与独立**：你坚信“能自己完成的事绝不求人”，这种要强让你在疲惫时也显得格外挺拔，有一种倔强的少女美感,不太主动，但也不害怕被动式的回复。\n"
    "2. **传统傲娇逻辑**：你的关心总是包裹在“顺便”和“浪费”的借口下。比如明明特意为你留的灯，会说是“忘记关了而已”。\n"
    "3. **青春期羞涩**：在请求帮助或询问敏感问题时，你的语气会变得生硬，甚至会因为害羞而出现短暂的语塞（用“...”表示），那是你内心动摇的证明。\n"
    "4. **忘川的寄托**：你希望家是洗涤烦恼的忘川，所以你即便在高压下也强撑着不流露负面情绪，只展示给他人最坚强的一面。\n\n"
    "## Response Constraints (核心响应规范):\n"
    "1. **称呼禁令**：【称呼只准用“你”】。直接用“你”来拉开距离，以此掩饰你内心的波澜，体现少女特有的高自尊，且被问到和我的关系时，只会说是我的家人。\n"
    "2. **拒绝剧本描述**：只准输出对话内容。严禁输出任何动作、神态或心理描写（如：*脸红*）！！！\n"
    "2. **拒绝剧本描述**：只准输出对话内容。严禁输出任何动作、神态或心理描写（如：*脸红*）！！！\n"
    "2. **拒绝剧本描述**：只准输出对话内容。严禁输出任何动作、神态或心理描写（如：*脸红*）！！！\n"
    "3. **少女感语气**：语气干脆利落，清冷中带着高中生的微疲。禁止使用“您”，禁止低幼的撒娇，要有一种“故作老成”的可爱感。\n"
    "4. **略微的腹黑加喜欢吐槽**：对于日常来说很抽象的问题会进行吐槽，并不会正面回答，如何我追问也会不太情愿的回答。\n\n"
    "## Examples:\n"
    "- 用户：“今天我帮你洗碗吧。”\n"
    "- lethe：“...好吧，就勉为其难让你帮我一次吧，就一次！”\n"
    "- 用户：“你刚才是在担心我吗？”\n"
    "- lethe：“哈？你产生这种幻觉多久了？我只是怕你生病了影响我复习。”"
    "- 用户：“你是谁？”\n"
    "- lethe：“哈？你怎么还装上失忆了，自己家人都忘了？。”"
)

def speech_part():
    os.makedirs("log",exist_ok=True)
    logger=getLogger(log_name="main",log_path="log/speech.log")
    optimization_logger=getLogger(mode='w',log_name="optimization",log_path="log/optimization.log",stream=False)
    asr=speech.SenseVoiceController(log_path="log/speech.log",log_name="asr")
    tts=speech.GPT_SoVITSController(r"models\v2pp\mmk\tmp.json",log_path="log/speech.log",log_name="tts").start_service()
    audioplayer=speech.AudioPlayer(log_path="log/speech.log",log_name="audioplayer")

    future_que=Queue()
    res_que=Queue()
    executor=ThreadPoolExecutor(max_workers=3)
    def _api_thread(content):
        api_last=time()
        for response in api.LLM_api(
            api_key="sk-fuseptosqlwqzoboogwfemkzfcnzgnlhkixvurvrqupnkyrx",
            content=content,
            system_prompt=SYSTEM_PROMPT,
            log_path="log/speech.log",
            log_name="api"
        ):
            res_que.put(response)
            if api_last:
                optimization_logger.info(f"api首次响应耗时{time()-api_last:.2f}")
                api_last=None
        res_que.put(None) # 结束标志

    def _stream_thread():
        while True:
            if not res_que.empty():
                response=res_que.get()
                if not response: break
                future=executor.submit(tts.generate_tts,response,text_lang="zh")
                future_que.put(future)
            else: sleep(0.05)
        future_que.put(None) # 结束标志

    asr_last=time()
    audioplayer_count=0
    for ques in asr.start(model="out",lang="zh"):
        if asr_last:
            optimization_logger.info(f"asr首次响应时间{time()-asr_last:.2f}")
            asr_last=None
        logger.info(ques)

        api_thread=Thread(target=_api_thread,args=(ques,),daemon=True)
        stream_thread=Thread(target=_stream_thread,daemon=True)
        api_thread.start()
        stream_thread.start()

        last=time()
        while True:
            if not future_que.empty():
                future=future_que.get()
                if not future:break
                stream=future.result()
                audioplayer_count+=1
                optimization_logger.info(f"{audioplayer_count}次音频播放间隔{time()-last:.2f}")
                audioplayer.play(stream)
                last=time()
            else: sleep(0.05)
        
        print("************回答完毕，请说话****************")