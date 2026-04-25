from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"

    AUTH_SERVICE_URL: str = "http://localhost:8001"
    CHAT_SERVICE_URL: str = "http://localhost:8002"
    DOCS_SERVICE_URL: str = "http://localhost:8003"

    class Config:
        env_file = ".env"


settings = Settings()
