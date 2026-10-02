/** Public-safe runtime configuration (all values come from VITE_* variables or build mode). */
export const appConfig = {
  apiUrl: import.meta.env.VITE_API_URL || "",
  /** Diagnostics page: on in dev, off in production unless explicitly enabled. */
  diagnosticsEnabled: import.meta.env.VITE_ENABLE_DIAGNOSTICS === "true" || (import.meta.env.DEV && import.meta.env.VITE_ENABLE_DIAGNOSTICS !== "false"),
  isDev: import.meta.env.DEV,
  version: import.meta.env.VITE_APP_VERSION || "dev",
};

export const EXAMPLE_QUESTIONS = [
  "What is Article 21 of the Constitution of India?",
  "What is the punishment for cheating under Section 420 IPC?",
  "Compare IPC 420 and BNS 318.",
  "Compare IPC 420 with BNS 318, explain the elements, identify the changes, and cite the statutory evidence.",
];
