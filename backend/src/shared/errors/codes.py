"""Every error code in the project. Codes are a public contract: never rename or reuse one."""
from enum import StrEnum


class ErrorCode(StrEnum):
    OK = "OK"

    # ---- Common ------------------------------------------------------------
    COMMON_BAD_REQUEST = "COMMON_BAD_REQUEST"
    COMMON_VALIDATION_ERROR = "COMMON_VALIDATION_ERROR"
    COMMON_NOT_FOUND = "COMMON_NOT_FOUND"
    COMMON_METHOD_NOT_ALLOWED = "COMMON_METHOD_NOT_ALLOWED"
    COMMON_CONFLICT = "COMMON_CONFLICT"
    COMMON_RATE_LIMITED = "COMMON_RATE_LIMITED"
    COMMON_INTERNAL_ERROR = "COMMON_INTERNAL_ERROR"
    COMMON_SERVICE_UNAVAILABLE = "COMMON_SERVICE_UNAVAILABLE"

    # ---- Auth --------------------------------------------------------------
    AUTH_NOT_AUTHENTICATED = "AUTH_NOT_AUTHENTICATED"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_PERMISSION_DENIED = "AUTH_PERMISSION_DENIED"

    # ---- Users -------------------------------------------------------------
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_EMAIL_TAKEN = "USER_EMAIL_TAKEN"
    USER_INACTIVE = "USER_INACTIVE"
    USER_WEAK_PASSWORD = "USER_WEAK_PASSWORD"

    # ---- Disputes ----------------------------------------------------------
    DISPUTE_NOT_FOUND = "DISPUTE_NOT_FOUND"
    DISPUTE_ALREADY_RESOLVED = "DISPUTE_ALREADY_RESOLVED"

    # ---- Policy ------------------------------------------------------------
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"

    # ---- Mediation ---------------------------------------------------------
    MEDIATION_FAILED = "MEDIATION_FAILED"

    # [kit:codes]
