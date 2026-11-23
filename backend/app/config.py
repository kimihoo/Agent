"""应用配置：全部通过环境变量覆盖，默认值保证开箱即用。"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
PARSED_DIR = DATA_DIR / "parsed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "app.db"))

# 演示环境自动生成并持久化 JWT 密钥
_SECRET_FILE = DATA_DIR / ".secret"
if os.environ.get("SECRET_KEY"):
    SECRET_KEY = os.environ["SECRET_KEY"]
elif _SECRET_FILE.exists():
    SECRET_KEY = _SECRET_FILE.read_text().strip()
else:
    SECRET_KEY = secrets.token_urlsafe(48)
    _SECRET_FILE.write_text(SECRET_KEY)

TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "12"))

# LLM / Embedding：配置了 OpenAI 兼容地址即启用真实模型，否则使用本地兜底
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
# 本地推理服务（如 Ollama）通常不需要密钥，只要有地址即启用
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))

EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", LLM_BASE_URL).rstrip("/")
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", LLM_API_KEY)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "512"))

LLM_ENABLED = bool(LLM_BASE_URL)
EMBEDDING_ENABLED = bool(EMBEDDING_BASE_URL and EMBEDDING_API_KEY)

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "480"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "80"))
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "6"))
