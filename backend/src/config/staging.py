from src.config.base import Environment, LogFormat, Settings


class StagingSettings(Settings):
    APP_ENV: Environment = "staging"
    DEBUG: bool = True
    LOG_FORMAT: LogFormat = "json"
