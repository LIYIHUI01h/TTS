import re
import json
import httpx
import asyncio
from typing import Any
from datetime import datetime
from mika.tool import getLogger
from openai import APIResponse, AsyncOpenAI
from llama_cloud import MetadataFilter, MetadataFilters
SiliconCloud_model = {
    "DeepSeek-V3": "deepseek-ai/DeepSeek-V3.2",
    "DeepSeek-R1": "deepseek-ai/DeepSeek-R1",
    "DeepSeek-R1 pro": "Pro/deepseek-ai/DeepSeek-R1",
    "Qwen2.5-72B": "Qwen/Qwen2.5-72B-Instruct-128K",
    "Qwen2-VL-72B":"Qwen/Qwen2-VL-72B-Instruct",
    "Qwen3.5-122B":"Qwen/Qwen3.5-122B-A10B",
    "Qwen2.5-7B":"Pro/Qwen/Qwen2.5-7B-Instruct",
    "Qwen3.5-4B":"Qwen/Qwen3.5-4B"
}

class async_LLM_api:
    def __init__(self, api_key,base_url="https://api.siliconflow.cn/v1",model=SiliconCloud_model["Qwen2.5-72B"],log_path=None, log_name=None):
        self.model=model
        self.logger = getLogger(log_path=log_path, log_name=log_name,mode='w')
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def start(self, message,json_data=True,interpt_event=None,min_length=8, weak_split=True):
        model=self.model
        try:
            if json_data:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=message,
                    stream=True,
                    response_format={"type": "json_object"}
                )
                try:
                    ff=False
                    buffer=""
                    action=""
                    last_pos=0
                    text_done=False
                    text_buffer = ""
                    strong_splits = {'。', '！', '？', '?', '!', '\n'} 
                    weak_splits = {'，', '；', '：', ',', ';', ':'} 
                    async for chunk in response:
                        if interpt_event.is_set():
                            ff=True
                            break
                        if not chunk.choices:continue
                        res=chunk.choices[0].delta.content
                        buffer+=res
                        if not text_done and '"text"' in buffer:
                            if last_pos == 0: 
                                marker_pos = buffer.find('"text"')
                                value_start = buffer.find('"', marker_pos + 6)
                                if value_start!=-1:last_pos=value_start+1
                                else: continue
                            tmp_buffer=buffer[last_pos:]
                            for char in tmp_buffer:
                                last_pos+=1

                                if char=='“' or char=='”':char='"'
                                elif char=="‘" or char=="’":char="'"
                                elif char=='：':char=':'

                                if char=='"': 
                                    text_done=True
                                    yield "text",text_buffer.strip()
                                    text_buffer=""
                                    break
                                elif char==']':
                                    action+=char
                                    yield "action",action[1:-1].strip()
                                    action=""
                                    continue
                                elif char=='[' or action:
                                    action+=char
                                    continue
                                text_buffer+=char
                                if  "..." in text_buffer  or (char in strong_splits and len(text_buffer.strip())>=5):
                                    yield "text",text_buffer.strip()
                                    text_buffer=""
                                elif char in weak_splits and len(text_buffer.strip())>=min_length and weak_split:
                                    yield "text",text_buffer.strip()
                                    text_buffer=""
                    if ff:yield "interpt", None
                    elif isinstance(buffer, str):
                        # buffer=buffer.replace('“','"').replace('：',':').replace("’","'").replace('”','"').replace("‘","'")
                        yield "json",json.loads(buffer)
                    else: 
                        yield buffer
                finally:
                    pass
            else:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=message,
                    stream=True,
                )
                try:
                    buffer = ""
                    action = ""
                    strong_splits = {'。', '！', '？', '?', '!', '\n'} 
                    weak_splits = {'，', '；', '：', ',', ';', ':', ' '} 
                    async for chunk in response:
                        if not chunk.choices:continue
                        text=chunk.choices[0].delta.content
                        if not text:continue

                        for char in text:
                            if char=='#': continue
                            elif char==']':
                                action+=char
                                yield "action",action[1:-1].strip()
                                action=""
                                continue
                            elif char=='[' or action:
                                action+=char
                                continue
                            buffer+=char
                            if char in strong_splits and len(buffer.strip())>=5:
                                yield "text",buffer.strip()
                                buffer=""
                            elif char in weak_splits and len(buffer.strip())>=min_length and weak_split:
                                yield "text",buffer.strip()
                                buffer=""
                finally:
                    pass
        except Exception as e:
            self.logger.error(f"❌ api请求出错：{e},{message}")

    async def start_nostream(self, message,include_json=False):
        model=self.model
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=message,
                stream=False,
                timeout=30
            )
        
            content=response.choices[0].message.content.strip()
            try:
                if include_json: content=content.replace('“','"').replace('：',':').replace("’","'").replace('”','"').replace("‘","'")
                json_data=json.loads(content)
                return json_data
            except:
                if include_json: content=content.replace('“','"').replace('：',':').replace("’","'").replace('”','"').replace("‘","'")
                return content
        except Exception as e:
            self.logger.error(f"❌ api请求出错：{e},{message}")

    async def start_nostream_json(self, message):
        model=self.model
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=message,
                stream=False,
                response_format={"type": "json_object"}
            )
            content=response.choices[0].message.content
            try:
                json_data=json.loads(content)
                return json_data
            except:
                return content
        except Exception as e:
            self.logger.error(f"❌ api请求出错：{e},{message}")

    async def warmup(self, interpt_event=None,content="hi", role="user", model=SiliconCloud_model["DeepSeek-V3"]):
        """预热：开启连接池并激活云端算子"""
        try:
            async with await self.client.chat.completions.create(
                model=model,
                messages=[{"role": role, "content": content}],
                max_tokens=1,
                stream=True
            ) as response:
                fl=True
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        if fl:
                            self.logger.info(f"✅ api预热成功，连接池已就绪")
                            fl=False
        except Exception as e:
            self.logger.error(f"❌ api预热请求出错：{e},hi")
            raise

    async def release(self):
        """仅在程序彻底关闭时调用"""
        await self.client.close()
        self.logger.info("🚪 API Client 已关闭")

embedding_model={
    "bge-m3":"BAAI/bge-m3"
}
reranker_model={
    "bge-m3":"BAAI/bge-reranker-v2-m3"
}

class async_embedding_api:
    def __init__(self,api_key,base_url="https://api.siliconflow.cn/v1",log_path=None,log_name=None):
        self.logger=getLogger(log_path=log_path,log_name=log_name)
        self.client=AsyncOpenAI(api_key=api_key,base_url=base_url)

    async def start(self,content,model=embedding_model["bge-m3"]):
        try:
            response = await self.client.embeddings.create(
                model=model,
                input=content,
                encoding_format="float"
            )
            return response.data[0].embedding
        except Exception as e:
            self.logger.error(f"❌ api请求出错：{e}")
            raise
            return None
        
class async_reranker_api:
    def __init__(self, api_key, base_url="https://api.siliconflow.cn/v1", log_path=None, log_name=None):
        self.api_key = api_key
        self.base_url=base_url

    async def start(self, query ,documents,model="BAAI/bge-reranker-v2-m3", top_n=3):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/rerank",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "query": query,
                        "documents": documents,
                        "top_n": top_n
                    },
                    timeout=60.0
                )
                
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            self.logger.error(f"❌ Reranker (HTTPX) 请求出错：{e}")
            raise
            return None