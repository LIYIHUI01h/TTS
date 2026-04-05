import sys
import wave
import psutil
import random
import logging
import asyncio
from datetime import datetime

class OutputFilter:
    def __init__(self, stream, blacklist):
        self.stream = stream
        self.blacklist = blacklist

    def write(self, data):
        if any(word in data for word in self.blacklist):return
        self.stream.write(data)
    def flush(self):
        self.stream.flush()

BLACKLIST_WORDS = ["微信公众号: JioNLP"]
sys.stdout = OutputFilter(sys.stdout, BLACKLIST_WORDS)
import jionlp as jio

def getLogger(level=logging.INFO,mode='a',log_path=None,log_name=None,stream=True):
    """返回对应的日志实例"""
    logger=logging.getLogger(str(log_name))
    logger.propagate = False
    if not logger.handlers:
        logger.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )  
        if stream:
            sh=logging.StreamHandler()
            sh.setFormatter(formatter)
            logger.addHandler(sh)
        if log_path:
            fh=logging.FileHandler(log_path,encoding="utf-8",mode=mode)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
    return logger

def save_wave(audio_data, file_path,channels = 1,sampwidth = 2,framerate = 32000):
    """音频保存"""
    channels = channels       # 单声道
    sampwidth = sampwidth     # 16位采样（2字节）
    framerate = framerate     # 采样率
    
    with wave.open(file_path, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sampwidth)
        wav_file.setframerate(framerate)
        wav_file.writeframes(audio_data)

def kill():
    """确保线程能结束的情况下清理所有线程"""
    current_process = psutil.Process()
    children = current_process.children(recursive=True)
    for child in children:
        try:
            if "python" in child.name().lower():
                child.terminate() 
                child.wait(timeout=3)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            try:
                child.kill() 
            except:
                pass

class MultiTimeParser:
    import jionlp as jio
    @staticmethod
    def parse(text):
        current_time = datetime.now()
        res_list = jio.ner.extract_time(text, time_base=current_time)
        
        parsed_results = []
        for item in res_list:
            detail = item.get("detail", {})
            time_detail = detail.get("time")
            
            if isinstance(time_detail, list) and len(time_detail) >= 2:
                if time_detail[0] and time_detail[1]:
                    parsed_results.append({                                                                                     
                        "s_time": str(time_detail[0]),
                        "e_time": str(time_detail[1])
                    })
            
        return parsed_results

class AsyncRandomTimer:
    def __init__(self,min_seconds,max_seconds,callback):
        self.min_seconds=min_seconds
        self.max_seconds=max_seconds
        self.callback=callback
        self._task=None

    async def run_timer(self):
        try:
            wait_time=random.uniform(self.min_seconds,self.max_seconds)
            await asyncio.sleep(wait_time)
            
            if asyncio.iscoroutinefunction(self.callback):await self.callback()
            else: self.callback()
        except Exception as e:
            print(e)
            pass
        
    def reset(self):
        if self._task:self._task.cancel()
        self._task=asyncio.create_task(self.run_timer())

    def stop(self):
        if self._task:
            self._task.cancel()
        
