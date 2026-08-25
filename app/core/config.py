from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://smartdocs:smartdocs@localhost:5432/smartdocsdb"
    )
    jwt_secret_key: str = "dev-only-change-me"  # 生产环境务必用 .env 覆盖
    jwt_algorithm: str = "HS256"
    # access_token_expire_minutes: int = 60 # 正式环境需恢复
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
