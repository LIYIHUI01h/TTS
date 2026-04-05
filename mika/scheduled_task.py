import base64
import io
import mss
import ctypes
import asyncio
import win32gui
import pyautogui
import win32process
from ddgs import DDGS
import ctypes.wintypes
from PIL import Image
from mika.api import * 
from mika.tool import getLogger
from mika.tool import AsyncRandomTimer

class IdleController:
    def __init__(self,text_que,flags):
        self.is_running=False
        self.flags=flags
        self.text_que=text_que
        self.click_event=asyncio.Event()
        self.click_timer=AsyncRandomTimer(10,60,self._click_task)
        self.screen_timer=AsyncRandomTimer(300,600,self.screen_task)
        self.timers=[self.click_timer,self.screen_timer]

    async def _click_task(self):
        if not self.click_event.set():
            self.click_event.set()

    async def click_task(self):
        if not self.click_event.set(): return
        self.text_que.put_nowait((self.flags.session_id,f"【idle lock】使用鼠标点击了你。根据以上信息主动找用户聊天吧！",[],False))
        self.click_event.clear()

    async def screen_task(self):
        def _get_target_area():
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
        
        try:
            loop = asyncio.get_event_loop()
            area, source_name = await loop.run_in_executor(None, _get_target_area)

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
            self.text_que.put_nowait((self.flags.session_id,f"【idle lock】闲置你挺久了,你已经截取了其鼠标指向的实时屏幕画面：{source_name}。根据以上信息主动找用户聊天吧！",[img_base64],False))
            await self.reset()
        except Exception as e:
            print(f"screen定时任务出错:{e}")

    async def run(self):
        print("计时任务开始")
        self.is_running=True
        for timer in self.timers:
            asyncio.create_task(timer.run_timer())

    async def reset(self):
        for timer in self.timers:
            timer.reset()

    async def stop(self):
        self.is_running=False
        for timer in self.timers:
            timer.stop()