/** Per-device preferences (localStorage). Nothing here is sensitive. */
import type { RetrievalProfile } from "@/types/api";

export type Theme = "system" | "light" | "dark";
const THEME_KEY = "legal-lens.theme";
const PROFILE_KEY = "legal-lens.profile";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

export function getTheme(): Theme {
  const t = read(THEME_KEY);
  return t === "light" || t === "dark" ? t : "system";
}
export function applyTheme(theme: Theme): void {
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
  write(THEME_KEY, theme === "system" ? null : theme);
}

export function getDefaultProfile(): RetrievalProfile | null {
  const p = read(PROFILE_KEY);
  return p === "FAST" || p === "BALANCED" || p === "DEEP" ? p : null;
}
export function setDefaultProfile(profile: RetrievalProfile | null): void {
  write(PROFILE_KEY, profile);
}

export function clearLocalData(): void {
  for (const key of [THEME_KEY, PROFILE_KEY, "legal-lens.sidebar"]) write(key, null);
}
