import os
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

class Settings(BaseSettings):
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    app_name: str = "AI Knowledge OS"
    admin_api_key: str = Field("demo-admin-key-2026", env="ADMIN_API_KEY")
    allowed_origins: List[str] = [
        "*",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]
    qdrant_url: Optional[str] = Field(None, env="QDRANT_URL")
    qdrant_api_key: Optional[str] = Field(None, env="QDRANT_API_KEY")
    langfuse_public_key: Optional[str] = Field(None, env="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(None, env="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field("https://cloud.langfuse.com", env="LANGFUSE_HOST")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v == "*":
                return ["*"]
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    class Config:
        extra = "ignore"

settings = Settings()
