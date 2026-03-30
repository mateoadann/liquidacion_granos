import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    CLIENT_SECRET_KEY = os.getenv("CLIENT_SECRET_KEY", SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://liquidacion:liquidacion@localhost:5432/liquidacion_granos",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CLIENT_CERTIFICATES_BASE_PATH = os.getenv(
        "CLIENT_CERTIFICATES_BASE_PATH", "/app/certificados_clientes"
    )
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Rate limiting
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_DEFAULT = "200 per minute"
    RATELIMIT_HEADERS_ENABLED = True
