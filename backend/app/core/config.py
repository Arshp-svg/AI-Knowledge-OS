from dotenv import load_dotenv
load_dotenv()

from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    app_name: str = "AI Knowledge OS"

    class Config:
        extra = "ignore"

settings = Settings()
print("ENV GROQ:", "GROQ_API_KEY" in __import__("os").environ)
