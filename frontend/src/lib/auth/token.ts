/**
 * Bearer token storage. The backend issues signed JWTs (no cookie session), so the token lives in
 * localStorage to survive refreshes. Trade-off documented in docs/SECURITY.md: XSS would expose it,
 * which is why markdown is rendered without raw HTML and no untrusted HTML is injected anywhere.
 */
const KEY = "legal-lens.token";
const EXPIRY_KEY = "legal-lens.token.expires";

export const tokenStore = {
  get(): string | null {
    try {
      const token = window.localStorage.getItem(KEY);
      const expires = Number(window.localStorage.getItem(EXPIRY_KEY) ?? 0);
      if (token && expires && Date.now() > expires) {
        this.clear();
        return null;
      }
      return token;
    } catch {
      return null;
    }
  },
  set(token: string, expiresInSeconds: number): void {
    try {
      window.localStorage.setItem(KEY, token);
      window.localStorage.setItem(EXPIRY_KEY, String(Date.now() + expiresInSeconds * 1000));
    } catch {
      /* storage unavailable (private mode): the session lasts for this page only */
    }
  },
  clear(): void {
    try {
      window.localStorage.removeItem(KEY);
      window.localStorage.removeItem(EXPIRY_KEY);
    } catch {
      /* ignore */
    }
  },
};
