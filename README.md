# 🛠️ Lethe 项目开发者手记 (Internal Dev Log)

## 🎨 UI 界面设计 (Interface Design)
待实现


## 🏗️ 核心逻辑架构 (System Architecture)

项目基于 **Asyncio 异步并发 + Threading 多线程混合框架** 构建，旨在实现“感知-决策-表达”的无缝衔接。

### 1. 感知层：耳朵 (ASR Module)

接入 `SenseVoiceController`

* **功能定义**：高精度实时语音转文字，以句为单位触发逻辑，实现伪流式交互。
* **运行模式**：支持 `in`（内部音频流）与 `out`（外部设备输入）双模式切换。
* **技术细节**：引入 `silence_threshold`（静默间隔阈值），智能过滤环境杂音与自身语音回授，确保监听动作的精准性。

### 2. 决策层：大脑 (LLM Module)

由 `api.async_LLM_api` 提供动力

* **人格注入**：通过核心 `SYSTEM_PROMPT` 硬编码 Lethe 的“傲娇高中生”人设，确保回复风格高度一致（高自尊、独立、毒舌）。
* **异步流式链路**：利用 `async for` 异步迭代器实时吞吐 API 响应，显著降低首字响应延迟（First Token Latency）。
* **硬打断机制**：通过 `flags["api_task"].cancel()` 物理切断逻辑链条，实现“即说即停”的强制闭嘴效果。

### 3. 表达层：嘴巴 (TTS Module)

基于 `GPT_SoVITSController`（待重构优化）

* **计算隔离**：通过 `ThreadPoolExecutor` 将 CPU 密集的推理任务从 `asyncio` 事件循环中剥离，防止音频合成导致的主逻辑阻塞。
* **参数配置**：依赖 `tmp.json` 进行模型预设与参考音频映射，目前正处于音色稳定性测试阶段。

### 4. 调度层：总线与状态控制 (`flags` & `Queues`)

* **数据流向**：
* `text_que`: ASR 识别结果至 API 决策层。
* `api_que`: API 决策流至 TTS 合成层。
* `future_que`: TTS 任务句柄至 AudioPlayer 播放层。


* **状态控制**：通过全局 `flags` 维护 `session_id` 和中断状态，确保对话次序的原子性与正确性。

---

## 🧹 资源清理机制 (Resource Lifecycle)

*解决“显存残留”的终极方案*

* **软着陆 (Soft Shutdown)**：向各级队列投放 `SHUTDOWN` 令牌，引导线程优雅退出。
* **硬清理 (Hard Kill)**：在 `finally` 块中强制调用 `kill()` 物理清除所有残留的 Python 子进程，确保 GPU 资源彻底回笼。

### 3. 记忆管理：大脑 (RAG)

基于llamaindex+adrant

query+short_memory ->llm时间、动作、心情等过滤器的提取->RAG进行向量检举->返回llm进行文本对话

## 📝 待开发模块蓝图 (Future Roadmap)
待实现功能：
1.UI设计
2.持久化记忆
3.3D模型控制
4.视觉感知
5.唤醒词模块
---