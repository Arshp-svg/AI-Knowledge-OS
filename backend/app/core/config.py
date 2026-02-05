from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "AI Knowledge OS"
    env: str = "dev"

    class Config:
        env_file = ".env"

settings = Settings()
