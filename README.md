这是一份为您重新整理的项目 README 功能详解。在保留专业技术术语的同时，侧重于系统逻辑与工程实现，适合有一定计算机基础（了解异步、RAG、Agent 概念）的人员阅读。

---

## 🛠️ 系统核心功能架构 (Technical Functionality)

本项目是一个集成了**多模态感知、自演化记忆、动态任务调度**的智能交互系统。通过异步非阻塞框架，实现了高性能的人机协作体验。

### 1. 异步非阻塞交互引擎 (Asynchronous Control Flow)
系统底层完全基于 `Python asyncio` 与 `PySide6` 的事件循环（Event Loop）融合构建。
* **并发任务调度**：利用 `qasync` 实现 UI 渲染与后台逻辑（如 LLM 推理、语音流解码、向量检索）的完全解耦。即使在进行重度计算时，界面依然能够保持 60FPS 的响应速度。
* **任务抢占与硬打断机制**：系统支持对正在运行的 `asyncio.Task` 进行实时监控。当 VAD（端点检测）发现用户抢话时，程序会立即调用 `.cancel()` 物理终止当前的语音合成与推理任务，确保交互的实时性。

### 2. 增强型感知系统 (Multi-source Perception)
系统通过听觉与视觉的双向输入，构建了完备的上下文感知能力。
* **声纹锁定语音识别 (ASR & Speaker Verification)**：
    * 集成 `SenseVoice` 实时语音转文字，并配合 `FSMN-VAD` 过滤非人声片段。
* **屏幕语义捕获 (Vision Agent)**：
    * 利用系统级 API（`mss` & `win32gui`）获取光标指向的活动窗口上下文。
    * 通过多模态视觉模型（如 `Qwen2-VL`）对屏幕截图进行语义解析，使 AI 具备处理“这行报错怎么解”或“分析这个图表”等具身智能任务的能力。

根据您提供的 `RAG.py` 源码逻辑，这一部分可以进一步深化，突出**异步非阻塞处理**、**知识去重与合并**以及**多维元数据过滤**的工程实现。

以下是针对“自演化长期记忆管理 (Evolutionary RAG)”部分的详细重写，保持了“严肃且技术性”的风格，同时深入解释了代码中的核心逻辑：

---

### 3. 自演化长期记忆管理 (Evolutionary RAG)

系统基于 **LlamaIndex** 与 **Qdrant** 构建了具备认知自演化能力的检索增强生成框架，解决了传统 RAG 记忆冗余及检索精度低的问题。

* **异步流式记忆持久化 (Asynchronous Consolidation)**：
    * **非阻塞排队机制**：系统通过 `asyncio.Queue` 构建记忆处理流水线。对话结束后，原始语料不会立即阻塞主进程，而是由后台 `MemoryManager` 异步提取核心事实。
    * **知识固化与去重 (Knowledge De-duplication)**：在存入向量库前，利用 LLM 对新旧记忆进行语义对比。若新对话包含已存在的认知事实，系统会执行**增量更新（Merge）**而非简单叠加；对于过时的冲突信息（如：用户更换了偏好），则执行**覆盖策略（Overwrite）**，确保检索到的始终是最新的结构化事实。
    * **复杂 JSON 结构解析**：针对 LlamaIndex 存储的 `_node_content` 复杂结构，系统实现了专用的递归提取逻辑，能从深层嵌套的 JSON 块中精准还原原始文本、心情倾向及交互时间戳。

* **时空多维检索与重排策略 (Multi-dimensional Retrieval)**：
    * **两阶段高精度检索**：
        1.  **初筛 (Coarse-grained)**：利用 `async_embedding_api` 将查询转化为 1024 维向量，在 Qdrant 空间中快速提取 `top_k=50` 的候选节点。
        2.  **精排 (Fine-grained)**：引入 `bge-reranker-v2-m3` 模型对候选集进行**深度语义重排序 (Reranking)**。通过计算 Query 与 Document 的交叉得分，剔除仅具有关键词重复但逻辑无关的噪声节点。
    * **时空维度元数据过滤 (Metadata Filtering)**：
        * **语义时间解析**：内置 `MultiTimeParser` 模块，能自动将用户口语中的时间谓语（如“前天”、“刚才”、“去年深秋”）解析为标准化的 UTC 时间范围。
        * **硬约束过滤**：解析结果被映射为 Qdrant 的 `MetadataFilters`（包含 `gte` 大于等于 / `lte` 小于等于）。在向量检索的底层阶段即完成“时间剪枝”，确保检索结果在逻辑上严格符合用户设定的时空上下文，彻底解决“记忆穿越”问题。
    * **动态 K 值分配**：根据用户查询的语义，系统会动态调整各语义的检索数量，确保在长文本摘要和短事实提取之间取得最佳平衡。

### 4. 动态任务调度智能体 (Agentic Workflow)
系统内置了一个基于微型 LLM 的意图分发器，将用户指令路由至不同的功能模块：
* **实时工具调用 (Function Calling)**：
    * **Web Search**：调用搜索引擎 API 获取实时资讯，弥补模型训练数据的滞后性。
    * **Environment API**：获取地理位置、实时气象等环境变量，辅助 AI 做出符合物理环境的决策。
* **多模态对齐输出**：系统在生成文本的同时，会携带特定的动作标签（Action Tags）。这些标签经过解析后，会同步驱动前端的 Live2D 模型或 UI 动效，实现“声、文、画”的高度同步。

### 5. 流式表达与反馈 (Output Orchestration)
* **流式 TTS 输出**：基于 `GPT-SoVITS` 的流式接口，采用异步迭代器实现音频切片的边生成边播放。
* **声学-视觉映射 (Lip-Sync)**：系统实时分析音频输出流的 RMS（均方根）振幅，通过 WebSocket 将能量值实时传递至前端，驱动虚拟形象的口型开合，实现音画同步。

---
## 🏗️ 技术栈汇总 (Tech Stack)
* **GUI 框架**：PySide6 (Qt for Python)
* **异步中枢**：asyncio, qasync
* **语音模型**：SenseVoice (ASR), GPT-SoVITS (TTS), FSMN-VAD
* **视觉/逻辑模型**：Qwen2.5 / Qwen2-VL (via SiliconCloud API)
* **向量索引**：LlamaIndex, Qdrant (Vector Database)
* **重排模型**：bge-reranker-v2-m3