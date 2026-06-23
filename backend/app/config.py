# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    wazuh_url: str = ""
    wazuh_user: str = ""
    wazuh_pass: str = ""
    secret_key: str = "dev-secret-change-in-production"
    environment: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()