"""Settings selection. `get_settings()` is called only by the container, main.py and manage.py."""
import os
from functools import lru_cache

from dotenv import dotenv_values

from src.config.base import ROOT_DIR, Settings
from src.config.development import DevelopmentSettings
from src.config.production import ProductionSettings
from src.config.staging import StagingSettings
from src.config.test import TestSettings

_SETTINGS_BY_ENV: dict[str, type[Settings]] = {
    "development": DevelopmentSettings,
    "staging": StagingSettings,
    "production": ProductionSettings,
    "test": TestSettings,
}


def current_env() -> str:
    env = os.getenv("APP_ENV") or dotenv_values(ROOT_DIR / ".env").get("APP_ENV") or "development"
    return env.lower()


@lru_cache
def get_settings() -> Settings:
    env = current_env()
    if env not in _SETTINGS_BY_ENV:
        raise RuntimeError(f"Unknown APP_ENV {env!r}. Expected one of {sorted(_SETTINGS_BY_ENV)}.")
    return _SETTINGS_BY_ENV[env]()


__all__ = ["Settings", "get_settings", "current_env"]
