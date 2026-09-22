from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql://postgres:YourSecurePassword123@localhost:5432/bt_sn_db"
    API_KEY: str = "BT_SN_PORTAL_SECRET_KEY_123"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
