from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str
    master_key_hex: str
    rpc_url: str
    relayer_private_key: str
    registry_addr: str
    consent_addr: str
    access_addr: str
    audit_addr: str

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    tavily_api_key: str = ""

    cors_origins: str = "http://localhost:3000"
    audit_from_block: int = 0

    # Local default preserves the existing backend/data directory.
    # On Render, set DATA_DIR=/var/data.
    data_dir: str = str(Path(__file__).resolve().parents[1] / "data")

    demo_auth_enabled: bool = False


settings = Settings()