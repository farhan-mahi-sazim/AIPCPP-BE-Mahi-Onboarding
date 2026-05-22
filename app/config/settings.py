from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "aipcpp_db"

    TEST_DB_PORT: int = 5435

    REDIS_URL: str = "redis://localhost:6379/0"

    # Cache Settings
    CACHE_ENABLED: bool = True
    CACHE_TTL_DEFAULT: int = 300
    CACHE_CONTENT_TTL: int = 3600

    # S3 / MinIO Settings
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "aipcpp-uploads"
    S3_USE_SSL: bool = False

    # Litellm / AI settings
    OPENAI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    LITELLM_MODEL: str = "gemini/gemini-2.5-flash"
    LITELLM_EMBEDDING_MODEL: str = "gemini/gemini-embedding-2"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Semantic Search Layer (3072 is standard for Gemini-2 embeddings)
    EMBEDDING_DIMENSION: int = 3072
    AI_ANALYSIS_TIMEOUT_SECONDS: int = 30
    MODEL_EMBEDDING_TIMEOUT_SECONDS: int = 20

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def database_url_sync(self) -> str:
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
