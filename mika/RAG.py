import os
import uuid
import json
import atexit
import asyncio
import aiofiles
import numpy as np
from collections import deque
from threading import Thread,Event
from mika.api import SiliconCloud_model
from mika.tool import getLogger
from llama_index.core.schema import NodeWithScore, TextNode
from llama_cloud import FilterOperator, MetadataFilter, MetadataFilters
from mika.tool import MultiTimeParser
from mika.api import async_LLM_api,async_embedding_api,async_reranker_api
from typing import Any, List
from dotenv import load_dotenv,set_key
from datetime import datetime
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core import StorageContext,VectorStoreIndex,Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient,AsyncQdrantClient
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.http.models import VectorParams, Distance

class MyEmbedding(BaseEmbedding):
    def __init__(self, api_instance: async_embedding_api, **kwargs: Any):
        super().__init__(**kwargs)
        self._api = api_instance

    async def _aget_query_embedding(self, query: str) -> List[float]:
        vector = await self._api.start(content=query)
        return vector if vector else []

    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        tasks = [self._api.start(content=text) for text in texts]
        results = await asyncio.gather(*tasks)
        return [r if r else [] for r in results]
    
    def _get_query_embedding(self, query: str) -> List[float]:
        return [] 

    def _get_text_embedding(self, text: str) -> List[float]:
        return []

class MemoryManager:
    def __init__(self, api_key, short_memory_size=5, top_k=50, top_n=5, 
                 add_insert_num=3, split_insert_num=2, user_name="璃依回", 
                 agent_name="null", collection_name="QianYi_memories", 
                 log_path="log/memory.log", log_name="memory_llm", 
                 model=SiliconCloud_model["Qwen2.5-72B"]):
        
        self.top_k = top_k
        self.top_n = top_n
        # 关键参数: m_list, k_map
        self.split_insert_num = split_insert_num
        self.add_insert_num = add_insert_num
        self.user_name = user_name
        self.agent_name = agent_name
        self.logger = getLogger(log_name=log_name, log_path=log_path, mode='w')
        self.model = model
        self.collection_name = collection_name
        
        self.small_api_llm = async_LLM_api(api_key=api_key, log_path=log_path, log_name=log_name, model=SiliconCloud_model["Qwen2.5-7B"])
        self.api_llm = async_LLM_api(api_key=api_key, log_path=log_path, log_name=log_name, model=self.model)
        self.api_embedding = async_embedding_api(api_key=api_key)
        self.api_reranker = async_reranker_api(api_key=api_key)
        Settings.embed_model = MyEmbedding(api_instance=self.api_embedding)

        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_mem_path = os.path.join(self.root_dir, "memories")
        
        if not os.path.exists(self.base_mem_path):
            os.makedirs(self.base_mem_path)

        self.db_path = os.path.join(self.base_mem_path, collection_name)
        self.short_memory_path = os.path.join(self.db_path, "short_memory.json")

        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)

        _temp_client = QdrantClient(path=self.db_path)
        try:
            if not _temp_client.collection_exists(collection_name):
                self.logger.info(f"检测到集合 {collection_name} 不存在，正在初始化...")
                _temp_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
                )
        finally:
            _temp_client.close()
            del _temp_client
        
        self.aclient = AsyncQdrantClient(path=self.db_path)
        self.vector_store = QdrantVectorStore(aclient=self.aclient, collection_name=collection_name)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)

        self.index = VectorStoreIndex.from_vector_store(
            self.vector_store, 
            storage_context=self.storage_context
        )

        initial_data = []
        if os.path.exists(self.short_memory_path):
            if os.path.getsize(self.short_memory_path) > 0:
                try:
                    with open(self.short_memory_path, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                        if isinstance(content, list):
                            initial_data = content
                except Exception as e:
                    self.logger.error(f"⚠️ 记忆文件损坏: {e}")
            else:
                self.logger.info("ℹ️ 记忆文件为空，初始化新记录。")
        
        self.short_memory_que = asyncio.Queue(maxsize=short_memory_size)
        for item in initial_data[-short_memory_size:]:
            self.short_memory_que.put_nowait(item)

        atexit.register(self._save_memory_at_exit)

        self.logger.info("✅ 记忆加载成功!")

        self.new_memory_que = asyncio.Queue()
        self.add_memory_done = asyncio.Event()
        self.update_dict = {}
        self.last_QA_summary = None

    async def switch_memory(self, flags):
        new_agent_name=flags.name
        new_collection_name=flags.memory_name
        prompt_path=flags.prompt_path
        self.logger.info(f"🔄 正在从 {self.collection_name} 切换到 {new_collection_name}...")
        
        await self.load_prompt(prompt_path)
        self._save_memory_at_exit()

        self.agent_name = new_agent_name
        self.collection_name = new_collection_name
        
        self.db_path = os.path.join(self.base_mem_path, new_collection_name)
        self.short_memory_path = os.path.join(self.db_path, "short_memory.json")
        
        print(f"DEBUG: 记忆库物理路径切换至 -> {os.path.abspath(self.db_path)}")

        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)
            
        _temp_client = QdrantClient(path=self.db_path)
        try:
            if not _temp_client.collection_exists(self.collection_name):
                self.logger.info(f"✨ 正在为新角色 {new_collection_name} 创建记忆集合...")
                _temp_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
                )
        finally:
            _temp_client.close()

        if hasattr(self, 'aclient'):
            await self.aclient.close()
        
        self.aclient = AsyncQdrantClient(path=self.db_path)
        self.vector_store = QdrantVectorStore(aclient=self.aclient, collection_name=self.collection_name)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        
        self.index = VectorStoreIndex.from_vector_store(
            self.vector_store, 
            storage_context=self.storage_context
        )

        await self._reload_short_memory()
        self.logger.info(f"✅ 记忆库已成功切换至: {new_collection_name}")

    async def _reload_short_memory(self):
        """清空当前队列并从新路径加载短时记忆数据"""
        while not self.short_memory_que.empty():
            try:
                self.short_memory_que.get_nowait()
            except asyncio.QueueEmpty:
                break
            
        initial_data = []
        if os.path.exists(self.short_memory_path):
            try:
                with open(self.short_memory_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        initial_data = content
            except Exception as e:
                self.logger.error(f"❌ 读取短时记忆文件失败: {e}")
        
        max_size = self.short_memory_que.maxsize
        for item in initial_data[-max_size:]:
            self.short_memory_que.put_nowait(item)
        
        self.logger.info(f"🧠 已载入 {len(initial_data[-max_size:])} 条短时记忆")
    
    def _save_memory_at_exit(self):
        """程序退出时执行"""
        try:
            data_to_save = list(self.short_memory_que._queue)
            if data_to_save:
                with open(self.short_memory_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, ensure_ascii=False, indent=2, default=str)
                self.logger.info(f"💾 短记忆已保存 {len(data_to_save)} 条对话")
        except Exception as e:
            self.logger.error(f"❌ 短记忆保存失败: {e}")

    async def get_embedding(self, text: str) -> List[float]:
        try:
            vector = await self.api_embedding.start(content=text)
            return vector if vector else []
        except Exception as e:
            self.logger.error(f"获取 Embedding 失败: {e}")
            return []

    async def load_core_memory(self,core_memory_path):
        if not os.path.exists(core_memory_path):
            self.logger.info(f"核心记忆文件缺失:{os.path.abspath(core_memory_path)}")
            raise
        async with aiofiles.open(core_memory_path,'r',encoding="utf-8")as f: 
            self.core_memory=await f.read()
        self.logger.info("✅核心记忆加载成功")

    async def load_prompt(self,dir,core_memory_path=None,include_core_memory=True):
        if core_memory_path and include_core_memory: await self.load_core_memory(core_memory_path)
        if not os.path.exists(dir):
            self.logger.info(f"系统提示词文件夹缺失:{os.path.abspath(dir)}")
            raise
        async with aiofiles.open(os.path.join(dir,"SYSTEM_PROMPT.md"),'r',encoding="utf-8")as f: 
            self.SYSTEM_PROMPT=await f.read()
        async with aiofiles.open(os.path.join(dir,"VL_SYSTEM_PROMPT.md"),'r',encoding="utf-8")as f: 
            self.VL_SYSTEM_PROMPT=await f.read()
        self.logger.info("✅ 提示词加载成功")

    async def do_query_summary_json(self,query):
        history_lines = []
        for ques, res,date in list(self.short_memory_que._queue):
            history_lines.append(f"[{date}] {self.user_name}: {ques};{self.agent_name}: {res}")
        context_str = "\n---\n".join(history_lines)
        prompt = f"""
            ## 角色：深度记忆检索意图拆解专家
            ## 任务：结合[上下文历史]与[当前提问]，如果本次对话与之前的主题符合就结合之前的对话和主题,否则独立的将提问拆解为最多3个核心“事实检索语义(summary),即进行查询意图分析，结合[上下文历史]以及当前对话中的纠正进行。

            ## [参考当前时间]：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

            ## [上下文历史]：
            {context_str if context_str else '（暂无历史）'}
            
            ## [当前提问]：
            {query} 

            ## 提炼规则：
            1. **多意图原子化**：若提问涉及多个客体（如张三、李四）或多个事项（如颜色、爱好），必须拆解为独立的检索句。最多拆分3个。
            2. **人物锚定**：每个语义必须包含“被询问的对象”姓名。
               - 错误：想知道他喜欢什么颜色
               - 正确：{self.agent_name}喜欢的颜色
            3. **去除干扰主体**：如果“{self.user_name}想知道{self.agent_name}的爱好”，检索意图应聚焦于客体，即“{self.agent_name}的爱好”，而不是包含发问者。
            4. **信息浓度增强**：不仅包含陈述，还要结合[上下文历史]补全代词（将“上次那个”补全为具体名字）以及当前正在进行的事件,最好包含当前的话题(比如历史中说在聊某部剧，然后现在在聊居中的某个人物，则总结中最好带上剧名)。
            5. **无效过滤**：若为毫无信息的寒暄、语气词（如“嘿嘿”、“你好”），intents 设为 ["无有效记忆点"]，dispatch 设为 false。

            ## 调度判定 (dispatch)：
            - 若涉及对过往事实、过往偏好、过去约定等的追溯(即需要进行回忆时)，则为 true。
            - 纯即时社交辞令、无需背景、即时话题的通用回答为 false。

            ## 输出JSON格式：
            {{
                "summary": ["高浓度语义1", "高浓度语义2", ...],
                "dispatch": true/false,
            }}

            ## 例子：
            - 提问：想想张三、李四喜欢吃什么。
            - 输出：{{
                "summary": ["张三喜好的食物", "李四喜好的食物"],
                "dispatch": true,
            }}

            - 提问：{self.agent_name}还记得{self.agent_name}和{self.user_name}的幸运色有什么区别吗？
            - 输出：{{
                "summary": ["{self.agent_name}的幸运色", "{self.user_name}的幸运色"],
                "dispatch": true,
            }}

            - 提问：{self.user_name}想知道{self.agent_name}的幸运色是什么？
            - 输出：{{
                "summary": ["{self.agent_name}的幸运色"],
                "dispatch": true,
            }}

            - 提问：{self.agent_name}知道《命运石之门》吗？
            - 输出：{{
                "summary": ["无有效记忆点"],
                "dispatch": false,
            }}


            ## 输出格式：
            {{
                "summary": ["高浓度语义1", "高浓度语义2", ...],
                "dispatch": true/false
            }}
            ## 注意：直接输出JSON，不要带Markdown代码块标签。
            """
        
        self.logger.info("查询提炼开始...")
        json_data=await self.small_api_llm.start_nostream(message=[{"role":"system","content":prompt},{"role":"user","content":f"当前提问：{query}"}])
        self.logger.info(f"查询提炼:{query}->{json_data}")
        return json_data

    async def do_QA_summary(self, content):
        history_lines = []
        for ques, res,date in list(self.short_memory_que._queue):
            history_lines.append(f"[{date}] {self.user_name}: {ques};{self.agent_name}: {res}")
        context_str = "\n---\n".join(history_lines)
        prompt = f"""
            ## 角色：深度记忆事实提炼专家
            ## 任务：结合[上下文历史][上轮对话summary参考],如果本次对话与之前的主题符合就结合之前的对话和主题,否则独立的将本次对话内容拆解为最多3个核心“事实检索语义(summary)”。
                    若[上轮对话summary参考]为空则自由发挥,否则请参考其中的主题，进行增删改。

            ## [参考当前时间]：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            ## [上下文历史]：
            {context_str if context_str else '（暂无历史）'}
            ## [上轮对话summary参考]：
            {self.last_QA_summary}

            ## [当前对话]：
            {content}

            ## 提炼规则（严格对齐检索侧逻辑）：
            1. **多意 atom 原子化**：若对话涉及多个客体（如张三、李四）或多个事项（如颜色、爱好），必须拆解为独立的检索句。最多拆分3个。
            2. **人物锚定**：每个语义必须包含“被描述的对象”姓名。
               - 错误：想知道他喜欢什么颜色
               - 正确：{self.agent_name}喜欢的颜色
            3. **去除干扰主体**：如果对话内容是“{self.user_name}询问了{self.agent_name}的爱好”，总结意图应聚焦于事实客体，即“{self.agent_name}的爱好”，而不是包含互动的过程描述。
            4. **信息浓度增强**：不仅包含陈述，还要结合对话背景补全代词（将“那个东西”补全为具体名字）以及当前正在进行的事件，最好包含当前的话题(比如历史中说在聊某部剧，然后现在在聊居中的某个人物，则总结中最好带上剧名)。
            5. **无效过滤**：若为毫无信息的寒暄、语气词（如“嘿嘿”、“你好”），summary 设为 ["无有效记忆点"]。

            ## 输出JSON格式：
            {{
                "summary": ["高浓度语义1", "高浓度语义2", ...]
            }}

            ## 例子（对齐查询侧输入格式）：
            - [当前对话]：[2026-03-11 10:15:00] 用户说：刚才路过那家萨莉亚人真多。{self.agent_name}说：因为便宜呀。
            - 输出：{{
                "summary": ["萨莉亚餐厅客流量大的原因", "萨莉亚餐厅的价格特点"]
            }}

            - [当前对话]：[2026-03-12 15:30:00] {self.user_name}说：{self.agent_name}还记得我喜欢的幸运色吗？{self.agent_name}说：是蓝色吧。
            - 输出：{{
                "summary": ["{self.user_name}的幸运色"]
            }}

            - [当前对话]：[2026-03-15 12:00:00] 用户说：嘿嘿。{self.agent_name}说：笑什么呀？
            - 输出：{{
                "summary": ["无有效记忆点"]
            }}

            ## 注意：直接输出JSON，不要带Markdown代码块标签。
            """
        
        self.logger.info("QA提炼开始...")
        data=await self.small_api_llm.start_nostream_json(message=[{"role":"system","content":prompt}])
        self.last_QA_summary=data
        self.logger.info(f"对话提炼:{content}->{data}")
        return data

    async def do_node_summary(self,node):
        current_summary=node.text
        QA_history="\n".join(node.metadata.get("QA",[]))

        prompt=f"""
            ## 任务角色：知识图谱与事实进化专家
            ## 任务目标：根据[原有记忆事实总结]与[待合并的对话历史]，将对话历史分类(1-3类))并生成对应的的记忆事实总结summary和该记忆事件总结下历史对话的总结consolidation。
            
            ## [参考时间]：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            ## [原有记忆事实总结]：{current_summary}
            ## [待合并的对话历史]：{QA_history}

            ## summary提取规则：
            1. **陈述事实**：必须输出主谓宾完整的纯文字陈述句（如“用户认为萨莉亚性价比高”）。
            2. **双角色识别**：必须精准识别并保留提问中涉及的角色。如果是璃依回的意图或动作，必须在 summary 中明确体现“璃依回”。
            3. **行为意图提取**：不仅提炼客体（如咖啡），还需提炼主体的具体意图（如：璃依回考虑买、璃依回打算送），不需要具体时间。。
            4. **剥离情绪**：去除“哈哈、太棒了、觉得”等瞬时词汇。
            5. **颗粒度**：提炼最核心的信息。如果仅仅是毫无信息量的寒暄（如“你好”、“又见面了”），请输出“无有效记忆点”。
            6. **多主题划分**：若当前内容涉及多个主题(1到3个主题)的对话,可以输出多个(1-3个)summary,并分类对话生成对应的consolidation
            7. **滚动式总结逻辑**：新的 summary 应当是原有总结的“升级版”而非“替代品”。你需要像更新维基百科条目一样，在原有词条的基础上增加细节（如：从“喜欢咖啡”进化为“喜欢深烘的曼特宁，但不爱加奶”），并剔除已过时的错误信息以及与原有总结不相关的信息。

            ## consolidation（记忆合并）进化逻辑：
            1. **体现纠偏过程**：若对话历史中出现了对原有事实的修正或观点的转变，summary应该体现出这点，如：
                - 实例1.
                [2023-3-13 11:12:23]璃依回说：我最喜欢黑色的衣服;{self.agent_name}说：那你应该最喜欢黑色吧
                [2023-3-14 11:12:23]璃依回说：记住了我最喜欢的颜色是白色;{self.agent_name}说：好的，记住了
                此时summary应该类似于:{self.agent_name}根据璃依回喜欢黑色衣服推测璃依回喜欢黑色，而璃依回指正说只是衣服喜欢黑色的，最喜欢的颜色是白色。
                - 实例2.
                [2023-3-13 11:12:23]璃依回说：我很讨厌跑步，太累了。;{self.agent_name}说：这样啊，那你可以试试别的运动
                [2025-3-14 11:12:23]璃依回说：我太喜欢跑步了，感觉身体变好了思路也更清晰了。;{self.agent_name}说：我当初推荐你坚持跑步没错吧。
                此时summary应该类似于:璃依回本来因为跑步太累而讨厌它，但在{self.agent_name}的建议下坚持后，又爱上了跑步，身体和思路都受益匪浅。
            2. **增量融合**：如果新对话只是补充了细节，则进行合并。
            -   示例：“璃依回准备考研” + “目标是西电” -> “璃依回正准备考研，目标院校是西安电子科技大学”。
            3. **事件分类**：根据内容演进逻辑，为每个 summary 分类出对应的QA,并对每类中所有QA对进行主谓宾完整的纯文字陈述句的总结 consolidation 
            5. **保留情感基调**：不创造情绪，但要记录对话中的“情感底色”。
                * 错误：璃依回感到非常非常开心（过度文学化）。
                * 正确：璃依回对该话题表现出明显的积极/认可态度；或：璃依回在讨论中表现出焦虑与纠结。
            5. 废弃无效信息：清理寒暄，保留硬核事实
            
            ## 输出格式要求：
            请直接输出 JSON 数组格式，以便程序解析，禁止输出任何其他解释文字。
            最多3个summary
            格式示例：
            [
                {{"summary": "事实陈述句1", "consolidation": "事件分类的总结"}},
                {{"summary": "事实陈述句2", "consolidation": "事件分类的总结"}},
                ...
            ]
            
            ## 最终约束：
            - 若无有效信息，返回空数组 []。
            - 必须严格遵守上述提取规则。
        """
        self.logger.info("node提炼开始...")
        data=await self.api_llm.start_nostream(message=[{"role":"system","content":prompt}])
        self.logger.info("node提炼完成")
        return data

    async def retrieve(self,query,top_k=50,filters=None):
        if not self.aclient.collection_exists(self.collection_name):return []
        retriever=self.index.as_retriever(similarity_top_k=top_k,filters=filters)
        nodes=await retriever.aretrieve(query)
        return nodes
        
    async def rerank(self,query,nodes,top_n=3):
        texts=[node.node.text for node in nodes]
        rerank_res=await self.api_reranker.start(query=query,documents=texts,top_n=top_n)
        best_nodes=[]
        if rerank_res and "results" in rerank_res:
            for item in rerank_res["results"]:
                idx=item["index"]
                node=nodes[idx]
                node.node.metadata["rerank_score"]=item["relevance_score"]
                best_nodes.append(node)
        return best_nodes
    
    async def query(self,query,images=[],query_score_threshold=0.6,show_message=False,do_query_split=True,is_search=False,user_query=True):
        self.logger.info("记忆检索开始...")
        # print(type(query),query)
        ttt=0
        if do_query_split and not is_search:
            t_query = query.replace("我", "{U}").replace("你", "{A}")
            tmp_query = t_query.replace("{U}", self.user_name).replace("{A}", self.agent_name)
            while True:
                try:
                    new_query=await self.do_query_summary_json(tmp_query)
                    need_memory=new_query.get("dispatch")
                    if self.user_name=="游客":need_memory=False
                    new_query=new_query.get("summary")
                    break
                except Exception as e:
                    ttt+=1
                    if ttt==3:
                        self.logger.error("❌ 当前llm返回出错，请切换模型")
                        raise
                    self.logger.info(f"do_query_summary_json失败{e},正在重试...")
                    await asyncio.sleep(0.1)
        else:
            need_memory=False
            new_query=["无有效记忆结点"]

        if isinstance(new_query, str):new_query = [new_query]
        
        # current_time_info = f"\n当前时间：[{datetime.now().strftime('%Y-%m-%d %H:%M:%S %A')}]"
        # message=[{"role":"system","content":self.SYSTEM_PROMPT+current_time_info}]
        message=[]
        filter_list = []

        if need_memory and not is_search:
            mtp=MultiTimeParser()
            time_infos=mtp.parse(query)
            s_ts,e_ts=[],[]
            if time_infos:
                s_ts = [datetime.strptime(ti["s_time"], "%Y-%m-%d %H:%M:%S").timestamp() for ti in time_infos]
                e_ts = [datetime.strptime(ti["e_time"], "%Y-%m-%d %H:%M:%S").timestamp() for ti in time_infos]
                start_time, end_time = min(s_ts), min(datetime.now().timestamp(), max(e_ts))
                if start_time < end_time:
                    filter_list.append(MetadataFilter(key="stimestamp", value=start_time, operator=FilterOperator.GREATER_THAN_OR_EQUAL_TO))
                    filter_list.append(MetadataFilter(key="etimestamp", value=end_time, operator=FilterOperator.LESS_THAN_OR_EQUAL_TO))
                    self.logger.info(f"时空感知激活：检索范围设定为 {datetime.fromtimestamp(start_time)} 至 {datetime.fromtimestamp(end_time)}")

            filter_list.append(MetadataFilter(key="memory_belonging", value=self.user_name, operator=FilterOperator.EQUAL_TO))
            final_filters = MetadataFilters(filters=filter_list) if filter_list else None

            async def get_dynamic_m_assignments(original_query, intents, total_quota=12):
                if not intents:return []
                tasks = [self.get_embedding(original_query)] + [self.get_embedding(i) for i in intents]
                embeddings = await asyncio.gather(*tasks)

                v_orig = np.array(embeddings[0])
                v_intents = [np.array(ve) for ve in embeddings[1:]]
                norm_orig = np.linalg.norm(v_orig)

                scores = []
                for v_i in v_intents:
                    norm_i = np.linalg.norm(v_i)
                    if norm_orig == 0 or norm_i == 0:
                        scores.append(0.1)
                        continue
                    score = np.dot(v_orig, v_i) / (norm_orig * norm_i)
                    scores.append(max(float(score), 0.1))

                total_score = sum(scores)
                m_list = [max(2, round((s / total_score) * total_quota)) for s in scores]
                return m_list

            m_list = await get_dynamic_m_assignments(query, new_query, total_quota=12)
            retrieve_tasks = [
                self.retrieve(query=intent, top_k=m, filters=final_filters) 
                for intent, m in zip(new_query, m_list)
            ]
            results = await asyncio.gather(*retrieve_tasks)
            unique_nodes_dict = {
                node.node.node_id: node 
                for node_list in results 
                for node in node_list
            }
            nodes = list(unique_nodes_dict.values())
            res=[]
            if nodes:
                n_intents = len(new_query)
                k_map = {1: 3, 2: 4, 3: 5}
                final_k = k_map.get(n_intents, 6)
                res=await self.rerank(query=tmp_query,nodes=nodes,top_n=final_k)
                res=[i for i in res if i.node.metadata.get("rerank_score", 0)>=query_score_threshold]
                if res: 
                    memory_text = f"""
                        ## 记忆运用高阶准则：
                        1. **深度信息提取**：现在是{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}。不要只看记忆里最近的一次回答！请从所有浮现的记录中提炼出关键事实（如：用户的真实姓名、身份、职业、具体爱好、过往经历）。
                        2. **禁止语义复读**：**绝对禁止复读记忆中 {self.agent_name} 说过的原话或类似的梗（如“改名字骗我”、“小伎俩”等）**。那是“过去”的你说的，现在的你应该根据记忆中的“事实”重新组织语言。
                        3. **忽略噪音**：如果记忆中某段对话只是在纠结某个词（比如反复争论改名、打招呼），请直接无视这些复读噪音，只提取其背后核心信息（即：用户的名字是璃依回）。
                        4. **身份确认逻辑**：当用户问“我是谁”时，你应该证明你记得他的多个特征，而不仅仅是一个名字。
                        5. **张冠李戴警告**：看清[说话人]！不要把用户的特性（如喜欢编程）说成是你的特性。
                        6. **自由发挥**：不要太拘束于记忆，可以从记忆从提取关键点结合当前的聊天背景组织语言。

                        ## 浮现的相关对话记录（按匹配度排序）：
                    """
                    memory_text+="\n".join([f"对话记录:[{node.metadata['display_time']}] {node.metadata.get('QA','')}" for node in res])
                else: memory_text = f"（经过回忆，{self.agent_name}没有在长期记忆中发现关于这件事的具体记忆碎片，{self.agent_name}可以试试在近期记忆中寻找，如果短期记忆中没有,{self.agent_name}可以回答忘了或不知道,请不要编造事件）\n"
                history_lines = []
                for ques, res,date in list(self.short_memory_que._queue):
                    history_lines.append(f"[{date}] {self.user_name}: {ques};{self.agent_name}: {res}")
                context_str = "\n---\n".join(history_lines)
                short_memory=f"这是{self.agent_name}的近期记忆(即最近发生的对话)：{context_str}"
                self.logger.info(memory_text+'\n'+short_memory)
                message.append({"role":"system","content":memory_text+'\n'+short_memory})
        
        for ques,res,date in list(self.short_memory_que._queue):
            message.extend([{"role":"user","content":ques},{"role":"assistant","content":res}])

        if user_query:current_text = f"[{self.user_name}]：{query}"
        else: current_text = f"[{self.user_name}{query}]"

        if not images:
            message.append({"role": "user", "content": current_text})
        else:
            content_list = [{"type": "text", "text": "这些是用户上传的图片"}]
            for img in images:
                content_list.append({
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"}
                })
            message.append({"role": "user", "content": content_list})
            message.append({"role": "user", "content": current_text})

        if show_message:
            self.logger.info(f"api传入提示词:{message}")
        return message

    async def add_short_memory(self,ques,res,date):
        if self.short_memory_que.full():
            await self.short_memory_que.get()
        self.short_memory_que.put_nowait([ques,res,date])
    
    async def add_memory(self,ques,llm_json,date,user_name):
        self.new_memory_que.put_nowait([ques,llm_json,date,user_name])

    async def _do_split_add(self, root_node, date, user,split_insert_threshold=0.8):
        try:
            new_summary = await self.do_node_summary(root_node)
            if not new_summary:return
            active_node=self.update_dict[root_node.node.id_]

            str_date = f"[{date}] "
            str_now = date.strftime("%Y-%m-%d %H:%M:%S")
            timestamp = int(date.timestamp())

            first_node_data = new_summary[0]
            first_text = first_node_data.get("summary", "")
            first_content = first_node_data.get("consolidation", "")

            if not first_text or "无有效记忆点" in first_text:return

            active_node.node.text=first_text
            active_node.node.metadata["QA"] = [str_date + first_content]
            active_node.node.metadata["last_time"] = str_now
            active_node.node.metadata["etimestamp"] = timestamp

            new_emb = await self.api_embedding.start(content=first_text)
            object.__setattr__(active_node.node, 'embedding', new_emb)

            root_id = root_node.node.id_

            for i in range(1, len(new_summary)):
                new_node_dict = new_summary[i]
                text = new_node_dict.get("summary", "")
                content = new_node_dict.get("consolidation", "")

                if not text or "无有效记忆点" in text: continue

                filters = MetadataFilters(
                        filters=[
                            MetadataFilter(key="memory_belonging", value=user,operator=FilterOperator.EQUAL_TO),
                        ]
                    )

                nodes = await self.retrieve(text, top_k=self.top_k, filters=filters)
                nodes=[node for node in nodes if node.node.id_!=root_id]

                if nodes: res = await self.rerank(query=text, nodes=nodes, top_n=1)
                if not res or res[0].node.metadata["rerank_score"]<split_insert_threshold:
                    new=TextNode(
                        id_=str(uuid.uuid4()),
                        text=text,
                        metadata={
                            "QA":[str_date+content],
                            "mood_change": active_node.node.metadata.get("mood_change", 0),
                            "special_info": active_node.node.metadata.get("special_info", "normal_chat"),
                            "display_time":date.strftime("%Y-%m-%d %H:%M:%S"),
                            "last_time":date.strftime("%Y-%m-%d %H:%M:%S"),
                            "stimestamp":int(date.timestamp()),
                            "etimestamp":int(date.timestamp()),
                            "memory_belonging":active_node.node.metadata.get("memory_belonging", self.user_name),
                        }
                    )
                    new.excluded_embed_metadata_keys=["QA","mood_change","special_info","display_time","last_time","stimestamp","etimestamp"]
                    new_node=NodeWithScore(node=new, score=1.0)
                    self.update_dict[new.id_]=new_node
                else:
                    for node in res:
                        if node.node.metadata["rerank_score"]<split_insert_threshold:continue
                        node_id=node.node.id_
                        if node_id not in self.update_dict: self.update_dict[node_id]=node
                        old_node=self.update_dict[node_id]
                        old_node.node.metadata["QA"].append(str_date+content)
                        old_node.node.metadata["last_time"]=date.strftime("%Y-%m-%d %H:%M:%S")
                        old_node.node.metadata["etimestamp"]=int(date.timestamp())
        except Exception as e:
            self.logger.error(f"❌ 记忆节点分裂失败:{e}")
        
    async def run_add_memory(self,merge_score_threshold=0.7,num_limit=10):
        while True:
            tri=await self.new_memory_que.get()
            self.logger.info(f"记忆添加任务：{tri}")
            if tri==None:break
            try:
                ques,llm_json,date,user=tri
                res=llm_json.get("text")
                mood_change=llm_json.get("mood_change",0)
                special_info=llm_json.get("special_info","normal_chat")
            except Exception as e:
                self.logger.info(f"llm格式出错，回滚这次对话：{ques}")
                continue
            if ques=="" and res=="":continue

            str_date=f"[{date}] "
            content=f"{self.user_name}说：'{ques}',{self.agent_name}说：'{res}'"

            ttt=0
            summary_list = []
            while True:
                try:
                    summary_json=await self.do_QA_summary(content)
                    summary_list = summary_json.get("summary", [])
                    break
                except Exception as e:
                    ttt+=1
                    if ttt==3:
                        self.logger.error("❌ 当前llm返回出错，请切换模型")
                        raise
                    self.logger.info(f"do_QA_summary失败{e}，正在重试...")
                    await asyncio.sleep(0.1)

            if not summary_list or "无有效记忆点" in summary_list or len(summary_list) == 0:
                self.logger.info("🍃 跳过无效记忆点更新")
                continue
            
            self.logger.info(f"开始添加记忆{content}")
            split_nodes=[]
            for text in summary_list:
                filters = MetadataFilters(
                    filters=[
                        MetadataFilter(key="memory_belonging", value=user,operator=FilterOperator.EQUAL_TO),
                    ]
                )
                nodes = await self.retrieve(text, top_k=self.top_k, filters=filters)
                if nodes: res=await self.rerank(query=text,nodes=nodes,top_n=self.add_insert_num)
                else: res=None

                if not res or res[0].node.metadata["rerank_score"]<merge_score_threshold:
                    new=TextNode(
                        id_=str(uuid.uuid4()),
                        text=text,
                        metadata={
                            "QA":[str_date+content],
                            "mood_change":mood_change,
                            "special_info":special_info,
                            "display_time":date.strftime("%Y-%m-%d %H:%M:%S"),
                            "last_time":date.strftime("%Y-%m-%d %H:%M:%S"),
                            "stimestamp":int(date.timestamp()),
                            "etimestamp":int(date.timestamp()),
                            "memory_belonging":user
                        }
                    )
                    new.excluded_embed_metadata_keys=["QA","mood_change","special_info","display_time","last_time","stimestamp","etimestamp"]
                    new_node=NodeWithScore(node=new, score=1.0)
                    self.update_dict[new.id_]=new_node
                    self.logger.info(f"新记忆结点添加成功:text:{new_node.node.text}")
                else:
                    for node in res:
                        if node.node.metadata["rerank_score"]<merge_score_threshold:continue
                        node_id=node.node.id_
                        if node_id not  in self.update_dict:self.update_dict[node_id]=node
                        active_node = self.update_dict[node_id]
                        new_qa_entry = str_date + content
                        if  new_qa_entry not in active_node.node.metadata["QA"]:
                            active_node.node.metadata["QA"].append(new_qa_entry)
                            active_node.node.metadata["last_time"]=date.strftime("%Y-%m-%d %H:%M:%S")
                            active_node.node.metadata["etimestamp"]=int(date.timestamp())
                            self.logger.info(f"记忆结点更新成功:text:{node.text}")
                            if len(active_node.node.metadata["QA"])>=num_limit:split_nodes.append(active_node)
            
            if split_nodes:
                seen_ids = set()
                unique_split_nodes = []
                for node in split_nodes:
                    if node.node.id_ not in seen_ids:
                        unique_split_nodes.append(node)
                        seen_ids.add(node.node.id_)

                for node in unique_split_nodes:
                    if node.node.id_ in self.update_dict:
                        await self._do_split_add(node, date, user)
                self.logger.info("✅ 记忆结点分裂成功!")
            
            try:
                update_nodes=[node.node for _,node in self.update_dict.items()]
                if update_nodes:await self.index.ainsert_nodes(update_nodes)
                self.update_dict={}
            except Exception as e:
                self.logger.error(f"❌ 记忆处理链崩溃: {e}")

        self.logger.info("add_memory任务结束")
        self.add_memory_done.set()

    async def show_memories(self,_print=True):
        self.logger.info("🏺 正在启动全量记忆扫描...")
        all_records=[]
        next_offset=None
        try:
            while True:
                records,next_offset=await self.aclient.scroll(
                    collection_name=self.collection_name,
                    with_payload=True,
                    with_vectors=False,
                    offset=next_offset,
                    limit=100
                )
                all_records.extend(records)
                if next_offset is None:break
            if not all_records:
                return []
            
            memory_list=[]
            for record in all_records:
                payload=record.payload
                text=payload.get("text","")
                if not text and "_node_content" in payload:
                    node_data=json.loads(payload["_node_content"])
                    text=node_data.get("text","")
                memory_list.append({
                    "id":record.id,
                    "text":text,
                    "QA":payload.get("QA",[]),
                    "stime": datetime.strptime(payload.get("display_time"), "%Y-%m-%d %H:%M:%S"),
                    "etime": datetime.strptime(payload.get("last_time"), "%Y-%m-%d %H:%M:%S"),
                    "mood_change":payload.get("mood_change",0),
                    "special_info":payload.get("special_info","normal_chat")
                })
            memory_list.sort(key=lambda x:x["etime"].timestamp())
            if _print:
                self.logger.info(f"📜 成功读取 {len(memory_list)} 条时间轴记忆：")
                for i,m in enumerate(memory_list):
                    self.logger.info(f"  [{i+1}] | {m['stime']} -- {m['etime']}| {m['text']}")
                    for QA in m["QA"]:
                        self.logger.info(f"-- {QA}")
            return memory_list
        except Exception as e:
            self.logger.error(f"❌ 记忆系统重构失败: {e}")
            return []
            