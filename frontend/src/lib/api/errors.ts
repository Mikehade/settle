/** Error codes the backend can return (`backend/src/shared/errors/codes.py`). A public contract. */
export const SERVER_ERROR_CODES = [
  "COMMON_BAD_REQUEST",
  "COMMON_VALIDATION_ERROR",
  "COMMON_NOT_FOUND",
  "COMMON_METHOD_NOT_ALLOWED",
  "COMMON_CONFLICT",
  "COMMON_RATE_LIMITED",
  "COMMON_INTERNAL_ERROR",
  "COMMON_SERVICE_UNAVAILABLE",
  "AUTH_NOT_AUTHENTICATED",
  "AUTH_INVALID_CREDENTIALS",
  "AUTH_TOKEN_EXPIRED",
  "AUTH_TOKEN_INVALID",
  "AUTH_PERMISSION_DENIED",
  "USER_NOT_FOUND",
  "USER_EMAIL_TAKEN",
  "USER_INACTIVE",
  "USER_WEAK_PASSWORD",
  "DISPUTE_NOT_FOUND",
  "DISPUTE_ALREADY_RESOLVED",
  "POLICY_NOT_FOUND",
  "MEDIATION_FAILED",
] as const;

/** Codes the client raises itself when there is no usable server response. */
export type ClientErrorCode = "NETWORK_ERROR" | "UNEXPECTED_RESPONSE";

// `string & {}` keeps autocomplete for known codes while tolerating codes added server-side later.
export type ErrorCode = (typeof SERVER_ERROR_CODES)[number] | ClientErrorCode | (string & {});

export interface FieldError {
  field: string | null;
  message: string;
}

const FALLBACK_MESSAGES: Partial<Record<ErrorCode, string>> = {
  NETWORK_ERROR: "Can't reach the Settle server. Check your connection and try again.",
  UNEXPECTED_RESPONSE: "The server sent a response Settle didn't understand.",
  COMMON_INTERNAL_ERROR: "Something went wrong on the server.",
  COMMON_SERVICE_UNAVAILABLE: "The server is temporarily unavailable. Try again shortly.",
  COMMON_RATE_LIMITED: "Too many requests. Wait a moment and try again.",
};

/** Every failed API call surfaces as one of these, with the backend's code and request ID. */
export class ApiError extends Error {
  override readonly name = "ApiError";
  readonly status: number;
  readonly code: ErrorCode;
  readonly fieldErrors: FieldError[];
  /** The backend's `X-Request-ID`, for matching a report to the server logs. */
  readonly requestId: string | null;

  constructor(options: {
    status: number;
    code: ErrorCode;
    message?: string;
    fieldErrors?: FieldError[];
    requestId?: string | null;
    cause?: unknown;
  }) {
    super(options.message || FALLBACK_MESSAGES[options.code] || "Request failed.", {
      cause: options.cause,
    });
    this.status = options.status;
    this.code = options.code;
    this.fieldErrors = options.fieldErrors ?? [];
    this.requestId = options.requestId ?? null;
  }

  /** Client errors (4xx) will not change on retry; network and server errors might. */
  get isRetryable() {
    return this.status === 0 || this.status >= 500 || this.status === 429;
  }

  static network(cause: unknown) {
    return new ApiError({ status: 0, code: "NETWORK_ERROR", cause });
  }

  /** Builds an error from a non-2xx response and its parsed body (the backend's envelope). */
  static fromResponse(response: Response, body: unknown) {
    const envelope = isRecord(body) ? body : {};
    const meta = isRecord(envelope.meta) ? envelope.meta : {};
    const requestId =
      response.headers.get("X-Request-ID") ??
      (typeof meta.request_id === "string" ? meta.request_id : null);

    return new ApiError({
      status: response.status,
      code: typeof envelope.code === "string" ? envelope.code : codeForStatus(response.status),
      message: typeof envelope.message === "string" ? envelope.message : undefined,
      fieldErrors: parseFieldErrors(envelope.errors),
      requestId,
    });
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** True when the backend rejected the caller's credentials or token. */
export function isUnauthorized(error: unknown) {
  return isApiError(error) && error.status === 401;
}

function codeForStatus(status: number): ErrorCode {
  if (status === 401) return "AUTH_NOT_AUTHENTICATED";
  if (status === 403) return "AUTH_PERMISSION_DENIED";
  if (status === 404) return "COMMON_NOT_FOUND";
  if (status === 409) return "COMMON_CONFLICT";
  if (status === 422) return "COMMON_VALIDATION_ERROR";
  if (status === 429) return "COMMON_RATE_LIMITED";
  if (status === 503) return "COMMON_SERVICE_UNAVAILABLE";
  if (status >= 500) return "COMMON_INTERNAL_ERROR";
  return "COMMON_BAD_REQUEST";
}

function parseFieldErrors(errors: unknown): FieldError[] {
  if (!Array.isArray(errors)) return [];
  return errors.filter(isRecord).map((error) => ({
    field: typeof error.field === "string" ? error.field : null,
    message: typeof error.message === "string" ? error.message : "Invalid value",
  }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
