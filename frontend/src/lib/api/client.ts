/**
 * The single HTTP transport. Every call goes through `request()`: base URL, bearer token, request id,
 * timeout/abort, JSON parsing and translation of the backend error envelope into `ApiError`.
 */
import type { ApiErrorBody } from "@/types/api";
import { tokenStore } from "@/lib/auth/token";

export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
export const API_PREFIX = "/api/v1";
const DEFAULT_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, requestId: string | null = null, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  /** True when the backend could not be reached at all (network/offline/timeout). */
  get isNetwork(): boolean {
    return this.status === 0;
  }
}

type Unauthorized = (error: ApiError) => void;
let onUnauthorized: Unauthorized | null = null;
/** Registered once by the auth provider; invoked on every 401 so the session is cleared centrally. */
export function setUnauthorizedHandler(handler: Unauthorized | null): void {
  onUnauthorized = handler;
}

export function newRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Skip the Authorization header (login/signup). */
  anonymous?: boolean;
}

export function buildUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path}`;
}

export function authHeaders(anonymous = false): Record<string, string> {
  const token = anonymous ? null : tokenStore.get();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Parse the backend error envelope; falls back to a generic error for non-JSON bodies. */
export async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("x-request-id");
  let body: ApiErrorBody | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = null;
  }
  if (body && typeof body === "object" && body.error && typeof body.error.code === "string") {
    return new ApiError(response.status, body.error.code, body.error.message, body.error.request_id ?? requestId, body.error.details);
  }
  const fallback: Record<number, [string, string]> = {
    401: ["authentication_failed", "Authentication required."],
    403: ["forbidden", "You are not allowed to do that."],
    404: ["not_found", "The requested resource was not found."],
    413: ["payload_too_large", "The request is too large."],
    429: ["rate_limited", "Too many requests. Please retry shortly."],
    502: ["llm_provider_error", "The language model provider failed to respond."],
    503: ["service_unavailable", "Legal Lens backend is currently unavailable."],
    504: ["timeout", "The request took too long to process."],
  };
  const [code, message] = fallback[response.status] ?? ["http_error", `Request failed (${response.status}).`];
  return new ApiError(response.status, code, message, requestId);
}

export async function fetchRaw(path: string, options: RequestOptions = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const forward = () => controller.abort(options.signal?.reason);
  options.signal?.addEventListener("abort", forward, { once: true });
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Request-ID": newRequestId(),
    ...authHeaders(options.anonymous),
    ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
    ...(options.headers ?? {}),
  };
  try {
    const response = await fetch(buildUrl(path), {
      method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
    if (response.status === 401 && !options.anonymous) {
      const error = await toApiError(response.clone());
      onUnauthorized?.(error);
    }
    return response;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError" && options.signal?.aborted) {
      throw error; // caller cancelled
    }
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    throw new ApiError(0, timedOut ? "timeout" : "network_error",
      timedOut ? "The request timed out." : "Legal Lens backend is currently unavailable. Check the server status.");
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", forward);
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetchRaw(path, options);
  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
