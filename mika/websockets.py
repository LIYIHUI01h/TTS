import asyncio
import json
import websockets
from mika.tool import getLogger


class WebSocketController:
    def __init__(self,host,port,log_path=None,log_name=None):
        self.host=host
        self.port=port
        self.logger=getLogger(log_path=log_path,log_name=log_name,stream=False)
        self.clients=set()

    async def _handler(self,websocket):
        self.clients.add(websocket)
        self.logger.info(f"客户端已连接：{websocket.remote_address}")
        try:
            async for message in websocket:
                self.logger.info(f"收到前端反馈：{message}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)
            self.logger.info(f"客户端已断开: {websocket.remote_address}")

    async def start(self):
        async with websockets.serve(self._handler,self.host,self.port):
            self.logger.info(f"🚀 通用服务已启动: ws://{self.host}:{self.port}")
            await asyncio.Future()

    async def emit(self,event_type,data):
        """
        通用发送方法
        :param event_type: 事件类型（如 'expression', 'motion', 'text'）
        :param data: 发送的具体内容（可以是字符串或字典）
        """
        if not self.clients:
            self.logger.warning("发送失败: 当前无客户端连接")
            return
        payload = json.dumps({
            "type": event_type,
            "data": data
        })
        await asyncio.gather(*[client.send(payload) for client in self.clients])
        self.logger.info(f"已推送事件[{event_type}]")

# async def my_business_logic(controller):
#     while True:
#         await asyncio.sleep(5)
#         await controller.emit("expression", "expressions/09脸红.exp3.json")
        
#         await asyncio.sleep(5)
#         await controller.emit("subtitle", "你好呀，我是你的虚拟助手！")

# async def main():
#     ctrl = WebSocketController()
    
#     await asyncio.gather(
#         ctrl.start(),
#         my_business_logic(ctrl)
#     )