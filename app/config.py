import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    local_database_url: str = os.environ["LOCAL_DATABASE_URL"]
    qdrant_url: str = os.environ.get("QDRANT_URL", "http://localhost:6333")
    cognito_region: str = os.environ["COGNITO_REGION"]
    cognito_user_pool_id: str = os.environ["COGNITO_USER_POOL_ID"]
    cognito_app_client_id: str = os.environ["COGNITO_APP_CLIENT_ID"]
    gemini_api_key: str = os.environ["GEMINI_API_KEY"]
    agent_model: str = os.environ.get("AGENT_MODEL", "gemini/gemini-3.1-flash-lite")
    cors_origins: list[str] = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")
    cloudwatch_log_group: str | None = os.environ.get("CLOUDWATCH_LOG_GROUP")
    cloudwatch_log_stream: str = os.environ.get("CLOUDWATCH_LOG_STREAM", "shopops-api")


settings = Settings()
