from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_string: str = ""

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_schema: str = "lead_intel"

    router_ai_base_url: str = "https://routerai.ru/api/v1"
    router_ai_key: str = ""
    router_ai_model: str = "router"

    min_participants: int = 50
    max_inactive_days: int = 90

    app_env: str = "production"
    app_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
