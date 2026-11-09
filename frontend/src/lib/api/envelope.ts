import { ApiError } from "./errors";

/**
 * Every backend response is `{ status, code, message, data, errors, meta }`. These helpers turn
 * an `api.GET(...)`-style call into its `data`, or throw an `ApiError`, so callers (query and
 * mutation functions) only ever see the payload.
 */
interface EnvelopeLike<T> {
  data?: T | null;
  meta?: Record<string, unknown> | null;
}

type ApiCall<T> = Promise<{ data?: EnvelopeLike<T>; error?: unknown; response: Response }>;

export interface PageMeta {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

export async function unwrap<T>(call: ApiCall<T>): Promise<NonNullable<T>> {
  const { data, response } = await settle(call);
  if (data?.data == null) {
    throw new ApiError({ status: response.status, code: "UNEXPECTED_RESPONSE" });
  }
  return data.data;
}

/** For list endpoints: the items plus the pagination the backend puts in `meta`. */
export async function unwrapPage<T>(call: ApiCall<T[]>): Promise<Page<T>> {
  const { data, response } = await settle(call);
  const meta = data?.meta;
  if (!Array.isArray(data?.data) || !meta) {
    throw new ApiError({ status: response.status, code: "UNEXPECTED_RESPONSE" });
  }
  return {
    items: data.data,
    meta: {
      page: Number(meta.page),
      pageSize: Number(meta.page_size),
      total: Number(meta.total),
      totalPages: Number(meta.total_pages),
    },
  };
}

async function settle<T>(call: ApiCall<T>) {
  let result: Awaited<ApiCall<T>>;
  try {
    result = await call;
  } catch (cause) {
    // Cancellation (a query that went stale, a page change) is not a failure: let it through.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw ApiError.network(cause);
  }
  if (!result.response.ok) throw ApiError.fromResponse(result.response, result.error);
  return result;
}
