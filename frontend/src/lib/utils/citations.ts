/** Citation helpers shared by chat, search and the evidence panel. */
const CITE = /\[([CM]\d+(?:\s*,\s*[CM]\d+)*)\]/g;

/** IDs cited in an answer, in order of first appearance. */
export function citedIds(text: string): string[] {
  const seen: string[] = [];
  for (const match of text.matchAll(CITE)) {
    for (const id of (match[1] ?? "").split(/\s*,\s*/)) {
      if (id && !seen.includes(id)) seen.push(id);
    }
  }
  return seen;
}

/**
 * Rewrite `[C1, C2]` into markdown links `[C1](#cite-C1) [C2](#cite-C2)` so the markdown renderer
 * can turn them into citation chips. Only IDs the backend returned become chips; the rest stay text.
 */
export function linkCitations(text: string, known: Set<string>): string {
  return text.replace(CITE, (whole, group: string) => {
    const ids = group.split(/\s*,\s*/);
    if (!ids.every((id) => known.has(id))) return whole;
    return ids.map((id) => `[${id}](#cite-${id})`).join(" ");
  });
}

/** Terms from the question worth highlighting inside an excerpt (≥ 4 letters, no stop words). */
const STOP = new Set(["what", "which", "when", "where", "does", "under", "with", "that", "this", "from", "about",
  "section", "article", "between", "explain", "compare", "difference", "punishment", "india", "indian", "legal"]);
export function highlightTerms(question: string): string[] {
  return Array.from(new Set(question.toLowerCase().match(/[a-z]{4,}/g) ?? [])).filter((t) => !STOP.has(t)).slice(0, 12);
}
