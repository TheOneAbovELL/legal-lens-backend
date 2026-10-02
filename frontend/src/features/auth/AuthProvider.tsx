import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/lib/api";
import { ApiError, setUnauthorizedHandler } from "@/lib/api/client";
import { tokenStore } from "@/lib/auth/token";
import type { LoginRequest, SignupRequest, UserOut } from "@/types/api";

export type AuthStatus = "loading" | "anonymous" | "authenticated";

interface AuthState {
  status: AuthStatus;
  user: UserOut | null;
  /** Set when the session was cleared by a 401 so the login page can explain why. */
  expiredNotice: boolean;
  login: (body: LoginRequest) => Promise<void>;
  signup: (body: SignupRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() => (tokenStore.get() ? "loading" : "anonymous"));
  const [user, setUser] = useState<UserOut | null>(null);
  const [expiredNotice, setExpiredNotice] = useState(false);
  const queryClient = useQueryClient();

  const clear = useCallback((expired: boolean) => {
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
    setExpiredNotice(expired);
    queryClient.clear();
  }, [queryClient]);

  // Validate a stored token on first load; an invalid one is dropped (never silently assumed valid).
  useEffect(() => {
    if (!tokenStore.get()) return;
    const controller = new AbortController();
    authApi.me(controller.signal)
      .then((me) => {
        setUser(me);
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) clear(true);
        else {
          // Backend unreachable: keep the token, treat as anonymous until it is reachable again.
          setStatus("anonymous");
        }
      });
    return () => controller.abort();
  }, [clear]);

  useEffect(() => {
    setUnauthorizedHandler(() => clear(true));
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  const accept = useCallback(async (token: string, expiresIn: number) => {
    tokenStore.set(token, expiresIn);
    const me = await authApi.me();
    setUser(me);
    setStatus("authenticated");
    setExpiredNotice(false);
  }, []);

  const login = useCallback(async (body: LoginRequest) => {
    const result = await authApi.login(body);
    await accept(result.access_token, result.expires_in);
  }, [accept]);

  const signup = useCallback(async (body: SignupRequest) => {
    const result = await authApi.signup(body);
    await accept(result.access_token, result.expires_in);
  }, [accept]);

  const logout = useCallback(() => clear(false), [clear]);

  const value = useMemo<AuthState>(() => ({ status, user, expiredNotice, login, signup, logout }),
    [status, user, expiredNotice, login, signup, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
