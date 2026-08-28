from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://activities:activities@db:5432/activities"
    api_cors_origins: str = "http://localhost:3000"
    app_username: str = "admin"
    app_password: str = "activities"
    app_token_secret: str = "local-dev-secret"
    api_enable_docs: bool = False
    api_allowed_hosts: str = "*"
    login_max_attempts: int = 5
    login_lockout_seconds: int = 900

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [host.strip() for host in self.api_allowed_hosts.split(",") if host.strip()]


settings = Settings()
