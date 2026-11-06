"""全局配置。

所有配置集中在 .env，通过环境变量读取，避免密钥写进代码。
换模型 = 改 .env 里的 LLM_* 三项，不改业务代码。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 从项目根目录加载 .env（backend/.env）
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """配置单例。"""

    # LLM（OpenAI 兼容接口，默认 DeepSeek，可切 Qwen 等）
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))

    # 服务
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # 数据目录（课程文件、SQLite 库）
    data_dir: Path = BASE_DIR / "data"

    @property
    def is_configured(self) -> bool:
        """是否已配置可用 API key。"""
        return bool(self.llm_api_key and not self.llm_api_key.startswith("sk-your"))


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
