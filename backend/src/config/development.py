from src.config.base import Environment, LogFormat, Settings


class DevelopmentSettings(Settings):
    APP_ENV: Environment = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: LogFormat = "console"
