from pydantic_settings import SettingsConfigDict

from src.config.base import Environment, LogFormat, Settings


class TestSettings(Settings):
    """Ignores .env so tests never touch a developer's database by accident."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    APP_ENV: Environment = "test"
    DEBUG: bool = True
    LOG_LEVEL: str = "WARNING"
    LOG_FORMAT: LogFormat = "console"
    LOG_ACCESS: bool = False
    DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"
    SECRET_KEY: str = "test-secret-key-that-is-long-enough-for-hs256"
