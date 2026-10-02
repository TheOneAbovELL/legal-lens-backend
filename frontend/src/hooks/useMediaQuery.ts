import { useEffect, useState } from "react";

/** Reactive media query (safe in tests: falls back to `false` when matchMedia is missing). */
export function useMediaQuery(query: string): boolean {
  const get = () => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false);
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, [query]);
  return matches;
}

export const BREAKPOINTS = {
  phone: "(max-width: 480px)",
  compact: "(max-width: 820px)",      // sidebar becomes a drawer
  noEvidencePane: "(max-width: 1100px)", // evidence becomes a drawer/sheet
};
