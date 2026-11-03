"""Every setting the app reads. Environment classes only override defaults.

Precedence (highest first): real environment variables, .env file, class defaults.
"""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

Environment = Literal["development", "staging", "production", "test"]
LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App -------------------------------------------------------------
    APP_NAME: str = "settle"
    APP_ENV: Environment = "development"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    DOCS_ENABLED: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = ""  # comma-separated

    # ---- Logging ---------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: LogFormat = "json"
    LOG_ACCESS: bool = True

    # ---- Database --------------------------------------------------------
    DATABASE_URL: str  # required
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False

    # ---- Auth ------------------------------------------------------------
    SECRET_KEY: str  # required
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_SECONDS: int = 60 * 30

    # ---- PayPal (sandbox) ------------------------------------------------
    # Left blank by default so the app boots without them; the PayPal client
    # only errors when a real call is attempted. Set these from your sandbox app.
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_WEBHOOK_ID: str = ""          # for webhook signature verification
    PAYPAL_HTTP_TIMEOUT: float = 30.0

    # ---- AWS Bedrock -----------------------------------------------------
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = (
        "arn:aws:bedrock:us-east-1:779056097161:inference-profile/global.anthropic.claude-opus-4-8"
    )
    BEDROCK_TEMPERATURE: float = 0.3     # mediation wants steadiness, not flair

    # ---- Mediation -------------------------------------------------------
    # Engine: False = native LLM + tools, True = LangGraph chain.
    MEDIATION_ENGINE_GRAPH: bool = False
    # Dispute source: "auto" tries the real Disputes API then falls back to
    # the seeded fixture; "paypal" forces real; "fixture" forces seeded.
    DISPUTE_SOURCE_MODE: Literal["auto", "paypal", "fixture"] = "auto"
    # Guardrail fallbacks (a seller's FairnessPolicy overrides these per case).
    GUARDRAIL_CONFIDENCE_THRESHOLD: float = 0.80
    GUARDRAIL_HUMAN_IN_LOOP_AMOUNT: float = 200.0
    GUARDRAIL_PARTIAL_REFUND_CEILING: float = 150.0

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
