from src.config.base import Environment, LogFormat, Settings


class ProductionSettings(Settings):
    APP_ENV: Environment = "production"
    DEBUG: bool = False
    DOCS_ENABLED: bool = False
    LOG_FORMAT: LogFormat = "json"
