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

    # API key para integración con liquidador externo
    LIQUIDADOR_API_KEY = os.getenv("LIQUIDADOR_API_KEY", "")
    LIQUIDADOR_API_ADMIN_TOKEN = os.getenv("LIQUIDADOR_API_ADMIN_TOKEN", "")

    # Stale job reconciliation — running jobs not updated within this window
    # are marked failed. Default 30 min; generous to avoid killing long jobs.
    STALE_JOB_TIMEOUT_SECONDS = int(os.getenv("STALE_JOB_TIMEOUT_SECONDS", "1800"))

    # Playwright per-action timeout (ms). Controls waits for selectors, clicks,
    # and table reads. Default 30 s is appropriate for most interactive steps.
    PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))

    # Playwright navigation + login timeout (ms). Used for page.goto() calls to
    # AFIP landing and LPG direct URL which can be slow at 3 AM. Default 60 s.
    PLAYWRIGHT_NAV_LOGIN_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_NAV_LOGIN_TIMEOUT_MS", "60000"))

    # Rate limiting
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_DEFAULT = "200 per minute"
    RATELIMIT_HEADERS_ENABLED = True
