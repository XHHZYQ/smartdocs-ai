from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    debug: bool = True  # 生产环境用 .env 覆盖为 False
    database_url: str = (
        "postgresql+asyncpg://smartdocs:smartdocs@localhost:5433/smartdocsdb"  # windows, 安装的是docker版本
        # "postgresql+asyncpg://smartdocs:smartdocs@localhost:5432/smartdocsdb"  # mac 安装的是命令行版本，不是docker版本
    )
    jwt_secret_key: str = "dev-only-change-me"  # 生产环境务必用 .env 覆盖
    jwt_algorithm: str = "HS256"
    # access_token_expire_minutes: int = 60 # 正式环境需恢复
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    redis_url: str = "redis://localhost:6379/0"
    # arq 任务队列用独立 db1，与缓存 db0 隔离
    arq_redis_url: str = "redis://localhost:6379/1"
    # 原始上传文件落盘目录（相对项目根；阶段10容器化时挂 volume 替换，以后可换 S3）
    upload_dir: str = "data/uploads"
    # embedding 分批大小：大文件切块后分批调外部 API，避免单次请求超限/超时
    embedding_batch_size: int = 32

    # arq worker 参数，WorkerSettings 读取
    arq_max_jobs: int = 10
    arq_job_timeout_seconds: int = 600
    arq_max_tries: int = 3

    chat_model: str = "deepseek-ai/DeepSeek-V4-Flash"

    # 限流配置:开发环境可关掉;enabled=False 时所有 @limiter.limit 装饰器自动放行
    rate_limit_enabled: bool = True
    rate_limit_default: str = "60/minute"


settings = Settings()
