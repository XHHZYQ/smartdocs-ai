import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# APP_ENV 决定从哪个 env 文件读配置：
#   local  -> .env.local   本机原生开发（uv run dev / make dev）
#   test   -> .env.test    测试（只放假值，进 git）
#   docker -> 无文件        本地 compose 栈，全部靠容器 environment 注入
#   prod   -> 无文件        线上 compose 栈，同上
# 容器里连接串一律用服务名（postgres:5432 / redis:6379），不读文件。
APP_ENV = os.getenv("APP_ENV", "local")
_ENV_FILES = {"local": ".env.local", "test": ".env.test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES.get(APP_ENV),  # docker/prod -> None，只认容器注入的 env
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===== 必填：随环境变化，一律不给默认值 =====
    # 缺失时启动即抛 ValidationError（fail-fast），而不是给一个可能不匹配的默认值
    database_url: str
    jwt_secret_key: str
    embedding_api_key: str

    # ===== 可选：与环境无关的常量，给默认值没问题 =====
    debug: bool = False  # 生产默认关；本地/测试由 env 文件开
    jwt_algorithm: str = "HS256"
    # access_token_expire_minutes: int = 60 # 正式环境需恢复
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 7

    redis_url: str = "redis://localhost:6379/0"
    # arq 任务队列用独立 db1，与缓存 db0 隔离
    arq_redis_url: str = "redis://localhost:6379/1"
    # 原始上传文件落盘目录（相对项目根；容器化时挂 volume 替换，以后可换 S3）
    upload_dir: str = "data/uploads"
    # embedding 分批大小：大文件切块后分批调外部 API，避免单次请求超限/超时
    embedding_batch_size: int = 32
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024

    # arq worker 参数，WorkerSettings 读取
    arq_max_jobs: int = 10
    arq_job_timeout_seconds: int = 600
    arq_max_tries: int = 3

    chat_model: str = "deepseek-ai/DeepSeek-V4-Flash"

    # 限流配置:开发环境可关掉;enabled=False 时所有 @limiter.limit 装饰器自动放行
    rate_limit_enabled: bool = True
    rate_limit_default: str = "60/minute"


settings = Settings()
