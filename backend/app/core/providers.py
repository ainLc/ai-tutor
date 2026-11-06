"""各大厂 OpenAI 兼容预设。页面选厂商即带出地址和常用模型名。"""

LLM_PROVIDERS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "hint": "官方兼容接口，默认推荐",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "hint": "需国际网络",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini"],
    },
    {
        "id": "qwen",
        "name": "通义千问",
        "hint": "阿里云百炼兼容模式",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
    },
    {
        "id": "moonshot",
        "name": "Kimi / Moonshot",
        "hint": "月之暗面",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-auto", "moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-turbo-preview"],
    },
    {
        "id": "zhipu",
        "name": "智谱 GLM",
        "hint": "BigModel 开放平台",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-flash", "glm-4-plus", "glm-4.5-flash"],
    },
    {
        "id": "siliconflow",
        "name": "硅基流动",
        "hint": "聚合多家开源模型",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
        ],
    },
    {
        "id": "volcengine",
        "name": "火山方舟",
        "hint": "模型名填接入点 ID",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k", "doubao-lite-32k"],
    },
    {
        "id": "minimax",
        "name": "MiniMax",
        "hint": "OpenAI 兼容 chat 接口",
        "base_url": "https://api.minimax.chat/v1",
        "models": ["MiniMax-Text-01"],
    },
    {
        "id": "ollama",
        "name": "Ollama 本地",
        "hint": "本机 11434，Key 可填 ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen2.5", "llama3.1", "deepseek-r1"],
    },
    {
        "id": "custom",
        "name": "自定义",
        "hint": "任意 OpenAI 兼容 /v1",
        "base_url": "",
        "models": [],
    },
]


def provider_by_id(pid: str) -> dict | None:
    for p in LLM_PROVIDERS:
        if p["id"] == pid:
            return p
    return None
