import { describe, expect, it } from "vitest";
import { citedIds, highlightTerms, linkCitations } from "@/lib/utils/citations";
import { describeError } from "@/lib/utils/errors";
import { relativeTime, truncate } from "@/lib/utils/format";
import { ApiError } from "@/lib/api/client";

describe("citation helpers", () => {
  it("extracts cited ids in order, once", () => {
    expect(citedIds("A [C2] b [C1, C2] c [M1] [C9]")).toEqual(["C2", "C1", "M1", "C9"]);
  });

  it("links only ids the backend returned", () => {
    const known = new Set(["C1", "C2"]);
    expect(linkCitations("x [C1] y [C1, C2] z [C7]", known)).toBe("x [C1](#cite-C1) y [C1](#cite-C1) [C2](#cite-C2) z [C7]");
  });

  it("picks highlight terms without stop words", () => {
    expect(highlightTerms("What is the punishment for cheating under Section 420 IPC?")).toEqual(["cheating"]);
  });
});

describe("formatting and error translation", () => {
  it("formats relative times", () => {
    const now = Date.parse("2026-10-02T12:00:00Z");
    expect(relativeTime("2026-10-02T11:59:50Z", now)).toBe("just now");
    expect(relativeTime("2026-10-02T11:30:00Z", now)).toBe("30 min ago");
    expect(relativeTime("2026-10-02T06:00:00Z", now)).toBe("6 h ago");
    expect(truncate("one two three four", 9)).toBe("one two…");
  });

  it("never shows raw transport errors to the user", () => {
    expect(describeError(new ApiError(0, "network_error", "x")).message).toMatch(/currently unavailable/);
    expect(describeError(new ApiError(429, "rate_limited", "x"))).toMatchObject({ retryable: true, title: "Slow down" });
    expect(describeError(new ApiError(503, "vector_store_error", "x")).title).toBe("Legal search unavailable");
    expect(describeError(new ApiError(502, "llm_provider_error", "x")).message).toMatch(/Search still works/);
    expect(describeError(new TypeError("Failed to fetch")).message).not.toMatch(/Failed to fetch/);
  });
});
