from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")

    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    default_model_provider: str = "gemini"

    admin_api_token: str = "change-me-to-a-long-random-string"

    daily_message_limit: int = 300

    # フロントエンドの公開URLをカンマ区切りで指定（例: https://healy-aimi.netlify.app）
    # 未設定の間は開発用に全許可（"*"）にしておく
    cors_allowed_origins: str = ""

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
