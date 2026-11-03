from src.config.base import Environment, LogFormat, Settings


class StagingSettings(Settings):
    APP_ENV: Environment = "staging"
    DEBUG: bool = False
    LOG_FORMAT: LogFormat = "json"
