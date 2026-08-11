from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://activities:activities@db:5432/activities"
    api_cors_origins: str = "http://localhost:3000"
    app_username: str = "admin"
    app_password: str = "activities"
    app_token_secret: str = "local-dev-secret"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


settings = Settings()
