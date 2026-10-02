import { ApiError } from "@/lib/api/client";

/** Human-readable text for typed backend errors; never surfaces raw transport errors. */
export function describeError(error: unknown): { title: string; message: string; retryable: boolean; code: string } {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "network_error":
        return { title: "Backend unavailable", code: error.code, retryable: true,
          message: "Legal Lens backend is currently unavailable. Check the server status." };
      case "timeout":
        return { title: "Timed out", code: error.code, retryable: true,
          message: "The request took too long. Please try again." };
      case "authentication_failed":
        return { title: "Sign in required", code: error.code, retryable: false,
          message: error.status === 401 && /invalid username or password/i.test(error.message)
            ? "Invalid username or password." : "Your session has expired. Please sign in again." };
      case "forbidden":
        return { title: "Not allowed", code: error.code, retryable: false, message: error.message };
      case "not_found":
        return { title: "Not found", code: error.code, retryable: false, message: error.message };
      case "conflict":
        return { title: "Already exists", code: error.code, retryable: false, message: error.message };
      case "rate_limited":
        return { title: "Slow down", code: error.code, retryable: true,
          message: "Too many requests. Please wait a moment and retry." };
      case "vector_store_error":
      case "retrieval_error":
      case "embedding_error":
      case "not_ready":
      case "service_unavailable":
        return { title: "Legal search unavailable", code: error.code, retryable: true,
          message: "Legal search is temporarily unavailable. The document index or embedding model is not ready." };
      case "llm_provider_error":
        return { title: "Answer generation unavailable", code: error.code, retryable: true,
          message: "The language model provider failed to respond. Search still works." };
      case "validation_error":
      case "invalid_query":
        return { title: "Invalid request", code: error.code, retryable: false, message: error.message };
      default:
        return { title: "Request failed", code: error.code, retryable: error.status >= 500, message: error.message };
    }
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return { title: "Cancelled", code: "cancelled", retryable: true, message: "The request was cancelled." };
  }
  return { title: "Something went wrong", code: "unknown", retryable: true,
    message: "An unexpected error occurred. Please try again." };
}
