import asyncio
import warnings
import httpx
import os
import io
import asyncio
import warnings
import httpx
import os
import io
import time
import json
import psutil
import subprocess
import logging
import aiofiles
import pyaudio
import torch
import miniaudio
import numpy as np
from threading import Thread
from queue import Queue
from funasr import AutoModel 
from threading import Thread
from mika.tool import getLogger
from concurrent.futures import ThreadPoolExecutor

class GPT_SoVITSController:
    """调用GPT-SoVITS接口"""
    def __init__(self, json_path,log_path="log/speech.log", log_name=None,inference_log_path=None,base_path="GPT-SoVITS"):
        self.log_path = log_path
        if log_name is None: log_name="GPT_SoVITSController"
        self.logger=getLogger(log_path=log_path,log_name=log_name,mode='w')
        self.inference_log_path=inference_log_path

        try:
            with open(json_path,'r',encoding="utf-8") as f:
                json_data=json.load(f)
            f.close()
            for key,value in json_data.items():
                setattr(self,key,value)
            self.logger.info("✅ json数据读取成功")
        except Exception as e:
            self.logger.error(f"❌ json数据读取失败:{e}")
            raise

        self.base_path = os.path.abspath(base_path)
        self.refer_wav_abspath = os.path.abspath(self.refer_wav).replace("\\", "/")

        self.api_url = "http://127.0.0.1:9880"
        self.config_path = os.path.abspath(os.path.join(self.base_path, "custom_config.json"))

        self.client=httpx.AsyncClient(timeout=60.0)

    async def _prepare_config(self):
        """生成版本对应配置文件"""
        config_data = {
            "gpt_path": os.path.abspath(self.gpt_model),
            "sovits_path": os.path.abspath(self.sovits_model),
            "is_half": True,
            "device": "cuda",
            "version": "v2",
            "cnhuhbert_base_path": os.path.abspath("GPT_SoVITS/pretrained_models/chinese-hubert-base"),
            "t2s_weights_path": os.path.abspath("GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"),
            "vits_weights_path": os.path.abspath("GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth"),
        }
        try:
            json_content=json.dumps(config_data,indent=4,ensure_ascii=False)
            async with aiofiles.open(self.config_path,'w', encoding="utf-8") as f:
                await f.write(json_content)
            self.logger.info(f"⚙️ 模型配置文件更新成功: {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"⚙️ 模型配置文件更新失败: {e}")
            return False

    async def kill_port_process(self, port=9880):
        """完全异步化的进程清理"""
        def find_pids():
            pids = []
            for conn in psutil.net_connections():
                if conn.status == psutil.CONN_LISTEN and conn.laddr.port == port:
                    pids.append(conn.pid)
            return pids

        pids = await asyncio.get_event_loop().run_in_executor(None, find_pids)

        if not pids:
            return

        for pid in pids:
            try:
                self.logger.info(f"正在清理端口 {port}, PID: {pid}")
                proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/T", "/PID", str(pid),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.wait()
            except Exception as e:
                self.logger.error(f"清理 PID {pid} 失败: {e}")
        
        await asyncio.sleep(1.0)

    async def start_service(self,interpt_event=None,timeout=80):
        await asyncio.get_event_loop().run_in_executor(None, self.kill_port_process, 9880)
        
        bat_file = os.path.join(self.base_path, "api-webui.bat")
        env = os.environ.copy() 
        env["PYTHONIOENCODING"] = "utf-8"

        def run_server():
            if self.inference_log_path is None:self.inference_log_path=self.log_path
            with open(self.inference_log_path, 'w', encoding="utf-8") as f:
                    self.logger.info("✅ run_server启动成功")
                    subprocess.Popen(
                        bat_file,
                        stdout=f, 
                        stderr=f,
                        env=env,
                        cwd=self.base_path, 
                        shell=True, 
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    )

        Thread(target=run_server, daemon=True).start()
        self.logger.info("⏳ 正在启动后端服务并加载模型...")

        for i in range(timeout):
            if interpt_event and interpt_event.is_set(): raise
            try:
                r = await self.client.get(self.api_url,timeout=1.0)
                if r.status_code < 500:
                    self.logger.info(f"✅ 服务已就绪 (耗时 {i}s)")
                    flag=await self.warm_up()
                    if flag: self.logger.info(f"✅ 模型启动成功!!!")
                    else: self.logger.error("❌ 模型预热失败!!!")
                    return self
                raise
            except Exception as e:
                await asyncio.sleep(0.5)
        
        self.logger.error("❌ 模型加载超时")
        return self
    
    async def warm_up(self):
        """预热模型，防止第一句合成太慢"""
        cnt=0
        while True:
            cnt+=1
            flag = await self.generate_tts("预热", text_lang=self.refer_lang, mode="warmup")
            if flag:
                self.logger.info("🔥 模型预热成功")
                return True
            if cnt>3: break
        self.logger.warning("⚠️ 预热失败")

        return False
    
    async def generate_tts(self, text, text_lang="auto", temperature=1, timeout=30, how_to_cut="按标点符号切", mode="stream", output_path="outputs/final.wav"):
        if mode not in ["file", "stream", "warmup"]: 
            raise ValueError(f"不支持模式: {mode}")
        
        cut_method_map = {
            "不切": "cut0",
            "凑四句一切": "cut1",
            "凑50字一切": "cut2",
            "按中文句号切": "cut3",
            "按标点符号切": "cut4",
            "按每一个标点符号切": "cut5"
        }
        split_method = cut_method_map.get(how_to_cut, "cut4")

        text_lang = text_lang or self.refer_lang
        params = {
            "text": text,
            "text_lang": text_lang if text_lang != "auto" else "zh",
            "ref_audio_path": self.refer_wav_abspath,
            "prompt_text": getattr(self, "refer_text", ""),
            "prompt_lang": getattr(self, "refer_lang", "zh"),
            "top_k": 5,
            "top_p": 1.0,
            "temperature": temperature,
            "text_split_method": split_method,
            "batch_size": 1,
            "speed_factor": 1.0,
            "media_type": "wav"
        }

        t0 = time.time()
        self.logger.info(f"🎤 发送合成请求: {text}")

        try:
            response =await self.client.get(f"{self.api_url}/tts", params=params, timeout=timeout)
            if response.status_code == 200:
                elapsed = f"{(time.time()-t0):.2f}s"
                if mode == "stream":
                    self.logger.info(f"✨ 流合成完成, 耗时: {elapsed}")
                    return response.content
                elif mode == "file":
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    async with aiofiles.open(output_path, "wb") as f:
                        await f.write(response.content)
                    self.logger.info(f"✨ 文件合成完成, 耗时: {elapsed},{os.path.abspath(output_path)}")
                    return True
                return True
            else:
                self.logger.error(f"❌ 合成失败, HTTP {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"❌ 请求发生异常: {e}")
            return False
        
    async def release(self):
        self.logger.info("🧹 正在释放资源...")
        self.kill_port_process(9880)
        await self.client.aclose()
        self.logger.info("🧹 释放资源完成！")

"""使用示例
async def main():
    tts=async_speech.GPT_SoVITSController(r"models\v2pp\mmk\tmp.json")
    await tts.start_service()

    text = "鳞兽真的很可爱呀。我很喜欢那种金灿灿的观赏鳞兽，用灌满水的透明袋子装起来后，朝着阳光观察它们吐泡泡的样子。"
    audio_data=await tts.generate_tts(text,temperature=1.1)
    if not audio_data: raise
    save_wave(audio_data,"outputs/tmp.wav")

    await tts.release()

asyncio.run(main())
"""

class AudioPlayer:
    _pygame_initialized=False
    def __init__(self, log_path=None, log_name=None, sample_rate=32000):
        
        if not AudioPlayer._pygame_initialized:
            import os
            import warnings
            import ctypes

            os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
            os.environ['SDL_VIDEODRIVER'] = 'dummy'
            os.environ["QT_PA_PLATFORM"] = "windows:dpiawareness=0"
            warnings.filterwarnings("ignore", category=UserWarning)

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

            global pygame, np, io, ThreadPoolExecutor
            import pygame
            import numpy as np
            import io
            from concurrent.futures import ThreadPoolExecutor

            AudioPlayer._pygame_initialized = True

        if log_name is None: log_name = "AudioPlayer"
        self.logger = getLogger(log_name=log_name, log_path=log_path)
        pygame.mixer.init(frequency=sample_rate, size=-16, channels=1, buffer=512)
        self.execute = ThreadPoolExecutor(max_workers=1)
        self._current_task = None  
        self._playing = False     
        self.logger.info(f"✅ 播放器初始化完成 (采样率: {sample_rate})")

    async def _wait_playback(self):
        """带有安全退出的等待逻辑"""
        try:
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pygame.mixer.music.stop()
            raise

    async def _play_stream(self, audio_bytes,ws_controller=None):
        if not audio_bytes or not isinstance(audio_bytes, bytes):
            return
        
        amps = self._calculate_amplitude_sequence(audio_bytes)

        loop = asyncio.get_running_loop()
        self._playing = True
        try:
            audio_io = io.BytesIO(audio_bytes)
            await loop.run_in_executor(self.execute, pygame.mixer.music.load, audio_io)
            pygame.mixer.music.play()
            if ws_controller:
                asyncio.create_task(self._sync_lip_to_web(amps, ws_controller))

            self.logger.info("🎤 正在播放内存音频流...")
            
            await self._wait_playback()
            
            self.logger.info("✅ 音频流播放完成")
            audio_io.close()
        except Exception as e:
            self.logger.error(f"❌ 流播放失败: {e}")
        finally:
            self._playing = False

    async def play(self, audio, mode="stream",ws=None):
        """确保同一时间只有一个音频在播放"""
        if self._playing:
            self.stop(0) 
            await asyncio.sleep(0.1)
        if mode == "file": 
            await self._play_file(audio)
        elif mode == "stream": 
            await self._play_stream(audio,ws)

    def stop(self, time_ms=0):
        """立即停止或淡出"""
        if pygame.mixer.get_init():
            if time_ms > 0:
                pygame.mixer.music.fadeout(time_ms)
            else:
                pygame.mixer.music.stop()
        self._playing = False

    def set_volume(self,volume):
        """设置音量(0.0 - 1.0)"""
        pygame.mixer.music.set_volume(volume)

    async def release(self):
        """释放资源"""
        pygame.mixer.quit()
        self.execute.shutdown()
        self.logger.info("🧹 播放器资源已释放")

    def _calculate_amplitude_sequence(self, audio_bytes, chunk_size=2048):
        data = np.frombuffer(audio_bytes, dtype=np.int16)
        amplitudes = []

        sensitivity = 12000.0 

        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            if len(chunk) == 0: continue

            rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
            normalized = min(1.0, rms / sensitivity)

            val = float(normalized) if normalized > 0.05 else 0.0
            amplitudes.append(val)

        return amplitudes
    
    async def _sync_lip_to_web(self, amps, ws):
        await asyncio.sleep(0.05)

        chunk_size = 2048 
        sample_rate = 32000
        interval = (chunk_size / sample_rate) * 0.95

        last_sent_val = 0
        for val in amps:
            if not self._playing: 
                break

            smooth_val = (val * 0.7) + (last_sent_val * 0.3)
            
            if abs(smooth_val - last_sent_val) > 0.02 or smooth_val > 0.05:
                await ws.emit("lip", {"value": float(smooth_val)})
                last_sent_val = smooth_val

            await asyncio.sleep(interval)

        await ws.emit("lip", {"value": 0.0})

"""使用说明
async def main():
    tts=async_speech.GPT_SoVITSController(r"models\v2pp\mmk\tmp.json")
    ap=async_speech.AudioPlayer()
    await tts.start_service()

    text = "鳞兽真的很可爱呀。我很喜欢那种金灿灿的观赏鳞兽，用灌满水的透明袋子装起来后，朝着阳光观察它们吐泡泡的样子。"
    audio_data=await tts.generate_tts(text,temperature=1.1)
    if not audio_data: raise

    play_task=asyncio.create_task(ap.play(audio_data))
    await play_task

    await tts.release()

asyncio.run(main())
"""

from functools import partial

class SenseVoiceController:
    """调用SenseVoice控制器"""

    emo_map = {
            "<|HAPPY|>": "😊 Happy",
            "<|SAD|>": "😔 Sad",
            "<|ANGRY|>": "😡 Angry",
            "<|NEUTRAL|>": "😐 Neutral",
            "<|FEARFUL|>": "😰 Fearful",
            "<|DISGUSTED|>": "🤢 Disgusted",
            "<|SURPRISED|>": "😮 Surprised",
        }

    tags_to_remove = {
        "<|zh|>", "<|en|>", "<|yue|>", "<|ja|>", "<|ko|>", "<|nospeech|>",
        "<|HAPPY|>", "<|SAD|>", "<|ANGRY|>", "<|NEUTRAL|>",
        "<|BGM|>", "<|Speech|>", "<|Applause|>", "<|Laughter|>",
        "<|FEARFUL|>", "<|DISGUSTED|>", "<|SURPRISED|>",
        "<|Cry|>", "<|EMO_UNKNOWN|>", "<|Sneeze|>", "<|Breath|>",
        "<|Cough|>", "<|Sing|>", "<|Speech_Noise|>",
        "<|withitn|>", "<|woitn|>", "<|GBG|>", "<|Event_UNK|>",
        "<|lang|>"
    }
    
    def __init__(self,
                 asr_model="iic/SenseVoiceSmall",
                 vad_model="fsmn-vad",
                 sv_model="iic/speech_campplus_sv_zh-cn_16k-common",
                 log_path=None,log_name=None):

        if not log_name:log_name="SenseVoiceController"
        self.logger=getLogger(log_name=log_name,log_path=log_path)
        self.executor=ThreadPoolExecutor(max_workers=5)
        self.asr_model=None
        self.vad_model=None
        self.sv_model=None
        self._asr_model=asr_model
        self._vad_model=vad_model
        self._sv_model=sv_model

        self.sample_rate=16000      # 标准采样率
        self.chunk_size_ms=150     # 处理每批次采样点数的时间
        self.chunk_size=int(self.chunk_size_ms*self.sample_rate/1000)
        self.target_embedding=None
        self.queue=asyncio.Queue()
        self.running=False
        self.reset()

        self.interpt=False

    async def load_models(self,interpt_event=None):
        loop=asyncio.get_running_loop()

        try:
            self.asr_model=await loop.run_in_executor(
                self.executor,
                partial(
                    AutoModel,
                    model=self._asr_model,trust_remote_code=True,
                    disable_pbar=True,disable_update=True,device="cuda:0"
                ),
            )
            if interpt_event and interpt_event.is_set(): raise
            self.vad_model=await loop.run_in_executor(
                self.executor,
                partial(
                    AutoModel,
                    model=self._vad_model,model_revision="v2.0.4",
                    disable_pbar=True,max_end_silence=200,
                    disable_update=True,device="cuda:0"
                )
            )
            if interpt_event and interpt_event.is_set(): raise
            self.sv_model =await loop.run_in_executor(
                self.executor,
                partial(
                    AutoModel,
                    model=self._sv_model, model_revision="v2.0.2",
                    disable_update=True, disable_pbar=True, device="cuda:0"
                )
            )
            self.logger.info("✅ 模型初始成功") 
        except Exception as e:
            self.logger.error("❌ 模型初始化失败")

    def reset(self):
        self.audio_buffer=np.array([],dtype=np.float32) # 音频总缓存
        self.audio_vad=np.array([],dtype=np.float32)    # 待识别音频缓存
        self.vad_cache={}
        self.asr_cache={}
        self.last_vad_beg=-1    # 上次有效识别的开始位置
        self.last_vad_end=-1    # 上次有效识别的结尾位置
        self.offset=0

    def process_output(self,text):
        mood="😐 Neutral"
        for tag,emoji_label in SenseVoiceController.emo_map.items():
            if tag in text:
                mood=emoji_label
                break
        
        output=text
        for tag in SenseVoiceController.tags_to_remove:
            output=output.replace(tag,"")
        output=output.strip()
        return output,mood

    async def load_temp(self,wav_path):
        if not os.path.exists(wav_path):
            self.logger.error(f"❌ 模板音频不存在! {os.path.abspath(wav_path)}")
            return False
        try:
            loop=asyncio.get_running_loop()
            res=await loop.run_in_executor(self.executor,partial(self.sv_model.generate,input=wav_path))
            if 'spk_embedding' in res:
                self.target_embedding = torch.tensor(res['spk_embedding']).to("cuda:0")
                self.logger.info("✅ 模板音频特征已提取")
                return True
        except Exception as e:
            self.logger.error(f"❌ 处理模板音频出错：{e}")
            return False

    async def asr_generate(self,audio_data,lang,use_itn=True):
        try:
            loop=asyncio.get_running_loop()
            return await loop.run_in_executor(
                self.executor,
                partial(
                    self.asr_model.generate,
                    input=audio_data,cache=self.asr_cache,language=lang,
                    use_itn=use_itn,batch_size_s=60,merge_vad=False,merge_length_s=15
                )
            )
        except Exception as e:
            self.logger.error(f"asr生成失败：{e}")

    async def compare(self,audio_data):
        if not self.target_embedding:return -1
        try:
            loop=asyncio.get_running_loop()
            res= await loop.run_in_executor(self.executor,partial(self.sv_model.generate,input=audio_data))
            if 'spk_embedding' in res:
                current_embedding = torch.tensor(res['spk_embedding']).to("cuda:0")
                cosine_sim = torch.nn.functional.cosine_similarity(
                    self.target_embedding, current_embedding, dim=-1
                )
                return float(cosine_sim.item())
        except Exception as e:
            self.logger.error(f"❌ 与模板音频比较出错：{e}")
            return 0.0

    async def generate(self,audio_chunk,rate,channels,lang):
        if len(audio_chunk) < 2: return
        data = np.frombuffer(audio_chunk, dtype=np.int16)

        if channels > 1:data = data.reshape(-1, channels).mean(axis=1).astype(np.int16)
        target_sr = 16000
        if rate != target_sr:
            num_samples = int(len(data) * target_sr / rate)
            data = np.interp(
                np.linspace(0, len(data), num_samples, endpoint=False),
                np.arange(len(data)),
                data
            ).astype(np.int16)

        new_data = data.astype(np.float32) / 32767.0
        self.audio_buffer = np.append(self.audio_buffer, new_data)

        while len(self.audio_buffer)>=self.chunk_size:
            chunk=self.audio_buffer[:self.chunk_size]
            self.audio_buffer=self.audio_buffer[self.chunk_size:]
            self.audio_vad=np.append(self.audio_vad,chunk)

            loop=asyncio.get_running_loop()
            vad_res=await loop.run_in_executor(
                self.executor,
                partial(
                    self.vad_model.generate,
                    input=chunk,cache=self.vad_cache,
                    is_final=False,chunk_size=self.chunk_size_ms
                )
            )
            
            if len(vad_res[0]["value"])>0:
                for segment in vad_res[0]["value"]:
                    if segment[0] > -1: self.last_vad_beg = segment[0]
                    if segment[1] > -1: self.last_vad_end = segment[1]

                    if self.last_vad_beg>-1 and self.last_vad_end>-1:
                        beg_idx = int((self.last_vad_beg - self.offset) * self.sample_rate / 1000)
                        end_idx = int((self.last_vad_end - self.offset) * self.sample_rate / 1000)
                        if beg_idx < 0: beg_idx = 0
                        if end_idx > len(self.audio_vad): end_idx = len(self.audio_vad)
                        if end_idx>beg_idx:
                            speech_data = self.audio_vad[beg_idx:end_idx]
                            asr_res=await self.asr_generate(speech_data,lang=lang)
                            sv_score=await self.compare(speech_data)
                            if asr_res:
                                text=asr_res[0]['text']
                                text,mood=self.process_output(text)
                                yield text,mood,sv_score
                        self.audio_vad=self.audio_vad[end_idx:]
                        self.offset+=(self.last_vad_end - self.offset)
                        self.last_vad_beg = -1
                        self.last_vad_end = -1
    
    async def _start(self,lang,temp=None, threshold=0.35,include_mood=True,mode="out",window=None):
        # await self.load_models()
        if mode=="in": import pyaudiowpatch as pa_module
        else: import pyaudio as pa_module
        pyaudio=pa_module

        self.target_embedding = None
        if mode == "out" and temp: await self.load_temp(temp)
        if not self.target_embedding: self.logger.info("无模板音频模式...")

        p = pyaudio.PyAudio()
        FORMAT = pyaudio.paInt16
        CHUNK = 4800
        CHANNELS = None
        RATE = None
        stream = None

        try:
            if mode == "out":
                self.logger.info("🎤 开始录音(外部声源)...")
                try:
                    default_input = p.get_default_input_device_info()
                    CHANNELS = int(default_input["maxInputChannels"]) 
                    RATE = 16000 
                except:
                    CHANNELS = 1
                    RATE = 16000

                stream = p.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK
                )
            elif mode == "in":
                try:
                    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                    
                    if not default_speakers["isLoopbackDevice"]:
                        for loopback in p.get_loopback_device_info_generator():
                            if default_speakers["name"] in loopback["name"]:
                                device_info = loopback
                                break
                        else:
                            device_info = p.get_default_wasapi_loopback_system_device()
                    else:
                        device_info = default_speakers
                except (AttributeError, OSError):
                    self.logger.error("❌ 无法获取内录设备。请确保已安装 pyaudiowpatch 且电脑正在播放声音。")
                    return
                self.logger.info(f"🎤 开始录音(内部声源): {device_info['name']}")
                
                RATE = int(device_info["defaultSampleRate"])
                CHANNELS = device_info["maxInputChannels"]
                
                stream = p.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    input_device_index=device_info["index"],
                    frames_per_buffer=CHUNK
                )
            else:
                self.logger.error(f"无当前录音模式{mode}")
                return

            while self.running:
                if window and window.page_chat.interpt:
                    self.runnning=False
                    self.interpt=True
                    break
                loop=asyncio.get_running_loop()
                data =await loop.run_in_executor(
                    self.executor,
                    partial(
                        stream.read,
                        CHUNK, exception_on_overflow=False
                    )
                )
                async for text, mood, score in self.generate(data, RATE, CHANNELS,lang=lang):
                    if window and window.page_chat.interpt:break
                    if self.target_embedding and score < threshold: continue
                    output = ""
                    if include_mood: output += f"|{mood}|"
                    output += text
                    await self.queue.put(output)
                    
        except Exception as e:
            self.logger.error(f"❌ 录音/处理时发生错误：{e}")
            import traceback
            traceback.print_exc()
        finally:
            self.logger.info("🛑 停止录音流...")
            if stream:
                if stream.is_active(): stream.stop_stream()
                stream.close()
            p.terminate()
            self.reset()
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self.queue.put_nowait(None)

    async def start(self,lang="auto",temp=None,threshold=0.35,include_mood=True,mode="out",window=None):
        while not self.queue.empty(): await asyncio.sleep(0.2)
        self.running=True
        # asyncio.create_task(self.monitor())
        self.main_task=asyncio.create_task(self._start(lang,temp,threshold,include_mood,mode,window))
        
        return self._get()

    async def _get(self):
        while True:
            if not self.running: await asyncio.sleep(0.2)
            output=await self.queue.get()
            if output is None:break
            yield output

    async def monitor(self, stop_key=']'):
        from pynput import keyboard
        loop=asyncio.get_running_loop()
        stop_event=asyncio.Event()

        def on_press(key):
            try:
                k = key.char if hasattr(key, 'char') else key.name
                if k == stop_key:
                    loop.call_soon_threadsafe(self.stop)
                    loop.call_soon_threadsafe(stop_event.set)
                    return False  
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        
        await stop_event.wait()

    def stop(self):
        if not self.running:return
        self.logger.info("停止语音读取")
        self.running=False

    def release(self):
        self.running = False
        
        self.asr_model = None
        self.vad_model = None
        self.sv_model = None
        self.target_embedding = None
        self.executor.shutdown(wait=False)
        self.reset()

        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

import asyncio
import base64
import time
import io
import wave
import numpy as np
import dashscope
from dashscope.audio.qwen_tts import SpeechSynthesizer

class QwenTTSController:
    def __init__(self, json_path, log_path="log/speech.log", log_name=None, inference_log_path=None, base_path="GPT-SoVITS"):
        self.log_path = log_path
        if log_name is None: log_name = "QwenTTSController"
        self.logger = getLogger(log_path=log_path, log_name=log_name, mode='w')
        
        self.api_key = "sk-ed9d05dbcfa64e319d51c78864a77c70" 
        dashscope.api_key = self.api_key
        self.voice = "Cherry"
        self.model = "qwen-tts"

    async def start_service(self, window):
        self.logger.info("正在初始化 Qwen-TTS 服务...")
        await self.generate_tts("验证", is_warmup=True)
        return self

    def _sync_streaming_call(self, text):
        return SpeechSynthesizer.call(
            model=self.model,
            api_key=self.api_key,
            text=text,
            voice=self.voice,
            format='pcm', 
            sample_rate=24000, 
            stream=True
        )

    async def generate_tts(self, text, text_lang="auto", is_warmup=False):
        t0 = time.time()
        pcm_data = b""
        try:
            loop = asyncio.get_event_loop()
            responses = await loop.run_in_executor(None, self._sync_streaming_call, text)

            for chunk in responses:
                if chunk.status_code == 200:
                    output = getattr(chunk, 'output', {})
                    audio_payload = output.get('audio', {}).get('data')
                    if audio_payload:
                        pcm_data += base64.b64decode(audio_payload)

            if pcm_data:
                audio_np = np.frombuffer(pcm_data, dtype=np.int16)
                
                target_rate = 32000
                source_rate = 24000
                num_samples = int(len(audio_np) * target_rate / source_rate)
                
                resampled_audio = np.interp(
                    np.linspace(0, len(audio_np), num_samples, endpoint=False),
                    np.arange(len(audio_np)),
                    audio_np
                ).astype(np.int16)

                with io.BytesIO() as wav_buffer:
                    with wave.open(wav_buffer, 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(target_rate)
                        wav_file.writeframes(resampled_audio.tobytes())
                    
                    full_wav_bytes = wav_buffer.getvalue()

                if not is_warmup:
                    self.logger.info(f"✅ 合成并校频成功 | 耗时: {time.time()-t0:.2f}s")
                
                return full_wav_bytes
            return None

        except Exception as e:
            self.logger.exception(f"Qwen-TTS 异常: {repr(e)}")
            return None

    async def release(self):
        self.logger.info("Qwen-TTS 资源已释放")