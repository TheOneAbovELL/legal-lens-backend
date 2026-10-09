/** Component behaviour of the redesigned primitives and features (no network). */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CitationChip, citationLabel } from "@/components/ui/Chip";
import { Drawer, Sheet } from "@/components/ui/Overlay";
import { ToastProvider } from "@/components/ui/Toast";
import { MemoryRouter } from "react-router-dom";
import { ResearchProgress } from "@/features/chat/ResearchProgress";
import { chatReducer, initialChatState } from "@/features/chat/chatReducer";
import { groupConversations } from "@/features/conversations/Sidebar";
import { EvidenceProvider, useEvidence } from "@/features/evidence/EvidenceContext";
import { EvidenceList, EvidenceTools } from "@/features/evidence/EvidencePanel";
import { EvidenceCard } from "@/features/evidence/EvidenceCard";
import { MappingComparison } from "@/features/mapping/MappingComparison";
import type { Citation } from "@/types/api";

const c1: Citation = { citation_id: "C1", document_id: "ipc", chunk_id: "a", title: "Indian Penal Code, 1860", act: "IPC", section: "420", source: "fixture", retrieval_sources: ["dense", "metadata"], excerpt: "Whoever cheats and thereby dishonestly induces the person deceived to deliver any property." };
const c2: Citation = { citation_id: "C2", document_id: "bns", chunk_id: "b", title: "Bharatiya Nyaya Sanhita, 2023", act: "BNS", section: "318", source: "fixture", retrieval_sources: ["dense"], excerpt: "Whoever cheats shall be punished." };
const c3: Citation = { citation_id: "C3", document_id: "con", chunk_id: "c", title: "Constitution of India", act: "CONSTITUTION", section: "21", source: "fixture", retrieval_sources: ["sparse"], excerpt: "No person shall be deprived of his life or personal liberty." };

describe("citation chips", () => {
  it("labels provisions the way lawyers read them", () => {
    expect(citationLabel(c1)).toBe("IPC §420");
    expect(citationLabel(c3)).toBe("Art. 21");
    expect(citationLabel({ act: null, section: null, case_name: "Maneka Gandhi v. Union of India", title: "SC" })).toBe("Maneka Gandhi v. Union of India");
  });

  it("is a keyboard-accessible button with a hover/focus source preview", async () => {
    const onClick = vi.fn();
    render(<CitationChip citation={c1} onClick={onClick} />);
    const chip = screen.getByRole("button", { name: "Citation C1: IPC §420" });
    const user = userEvent.setup();
    await user.tab();
    expect(chip).toHaveFocus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Whoever cheats");
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});

function Harness() {
  const ev = useEvidence();
  return (
    <>
      <button type="button" onClick={() => ev.show("m1", [c1, c2, c3], "whoever cheats under IPC")}>show</button>
      <EvidenceTools />
      <EvidenceList />
    </>
  );
}

describe("evidence panel", () => {
  it("lists cited passages, selects on click and steps with next/previous", async () => {
    render(<MemoryRouter><ToastProvider><EvidenceProvider><Harness /></EvidenceProvider></ToastProvider></MemoryRouter>);
    const user = userEvent.setup();
    expect(screen.getByText(/No evidence selected/)).toBeInTheDocument();
    await user.click(screen.getByText("show"));
    const cards = screen.getAllByTestId("source-card");
    expect(cards).toHaveLength(3);
    expect(screen.getByText(/Cited for:/)).toHaveTextContent("whoever cheats under IPC");
    await user.click(cards[1]!);
    expect(cards[1]).toHaveAttribute("aria-current", "true");
    await user.click(screen.getByRole("button", { name: "Next citation" }));
    expect(cards[2]).toHaveAttribute("aria-current", "true");
    await user.click(screen.getByRole("button", { name: "Next citation" }));
    expect(cards[0]).toHaveAttribute("aria-current", "true"); // wraps
    await user.click(screen.getByRole("button", { name: "Previous citation" }));
    expect(cards[2]).toHaveAttribute("aria-current", "true");
    expect(within(cards[0]!).getByText(/Exact match for a provision named/)).toBeInTheDocument();
    expect(within(cards[0]!).getByText("cheats", { selector: "mark" })).toBeInTheDocument();
  });

  it("labels a concurring or dissenting opinion and never a majority one", () => {
    const concurring: Citation = {
      citation_id: "C9", document_id: "joseph_shine_2018", chunk_id: "p7", title: "Joseph Shine v. Union of India",
      case_name: "Joseph Shine v. Union of India", case_citation: "(2019) 3 SCC 39", court: "Supreme Court",
      opinion_type: "concurring", opinion_author: "D.Y. Chandrachud",
      cite_as: "Joseph Shine v. Union of India, (2019) 3 SCC 39, para 7 (per D.Y. Chandrachud, concurring)",
      paragraph: 7, source: "qdrant", retrieval_sources: ["dense"], excerpt: "Sexual agency of women.",
    };
    const majority: Citation = { ...concurring, citation_id: "C10", opinion_type: "majority", opinion_author: "Dipak Misra" };
    render(
      <MemoryRouter><ToastProvider>
        <EvidenceCard citation={concurring} /><EvidenceCard citation={majority} />
      </ToastProvider></MemoryRouter>,
    );
    const notes = screen.getAllByTestId("opinion-note");
    expect(notes).toHaveLength(1);
    expect(notes[0]).toHaveTextContent("Concurring opinion of D.Y. Chandrachud — not the Court's holding.");
    expect(screen.getAllByText(/\(2019\) 3 SCC 39/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/para 7/).length).toBeGreaterThan(0);
  });
});

describe("overlays", () => {
  it("drawer and sheet close on Escape and return focus", async () => {
    const onClose = vi.fn();
    const { rerender } = render(<><button type="button">before</button><Drawer open title="Conversations" onClose={onClose}><button type="button">inside</button></Drawer></>);
    const user = userEvent.setup();
    expect(screen.getByRole("dialog", { name: "Conversations" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    rerender(<><button type="button">before</button><Sheet open title="Evidence" onClose={onClose}><button type="button">inside</button></Sheet></>);
    expect(screen.getByRole("dialog", { name: "Evidence" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close Evidence" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("mapping comparison", () => {
  it("renders exact, ambiguous and missing mappings truthfully", () => {
    render(<MappingComparison alerts={[
      { old: "IPC 420", new: "BNS 318(4)", effective: "2024-07-01", mapping_type: "exact", subject: "Cheating", verification_status: "curated_unverified", provenance: "dataset" },
      { old: "IPC 377", new: null, effective: "2024-07-01", mapping_type: "no_mapping", verification_status: "curated_unverified", provenance: "dataset" },
      { old: "IPC 300", new: "BNS 101", effective: null, mapping_type: "ambiguous", verification_status: "curated_unverified", provenance: "dataset+graph" },
    ]} />);
    const card = screen.getByTestId("mapping-card");
    expect(card).toHaveTextContent("IPC 420");
    expect(card).toHaveTextContent("BNS 318(4)");
    expect(card).toHaveTextContent("exact mapping");
    expect(card).toHaveTextContent("No equivalent");
    expect(card).toHaveTextContent("Sources disagree");
  });
});

describe("research progress", () => {
  it("shows backend-planned aspects and marks them done after retrieval", () => {
    let s = chatReducer(initialChatState(), { type: "send", query: "Compare", userId: "u", assistantId: "a", now: "2026-10-02T10:00:00Z" });
    s = chatReducer(s, { type: "event", assistantId: "a", event: { type: "plan", method: "rule", subqueries: [
      { id: "q0", query: "Compare IPC 420 and BNS 318", purpose: "original" },
      { id: "q1", query: "IPC 420", purpose: "IPC provision" },
      { id: "q2", query: "BNS 318", purpose: "BNS provision" },
    ] } });
    const { rerender } = render(<ResearchProgress phase={s.phase} stage={s.stage} />);
    const list = screen.getByTestId("research-aspects");
    expect(list).toHaveTextContent("Researching 3 legal aspects");
    expect(within(list).getAllByLabelText("pending")).toHaveLength(3);
    s = chatReducer(s, { type: "event", assistantId: "a", event: { type: "retrieval", candidates: 20, sources: { dense: 10 } } });
    rerender(<ResearchProgress phase={s.phase} stage={s.stage} />);
    expect(within(screen.getByTestId("research-aspects")).getAllByLabelText("done")).toHaveLength(3);
    expect(screen.getByTestId("status-row")).toHaveTextContent("Reviewing 20 passages");
  });
});

describe("conversation grouping", () => {
  it("groups by day relative to now", () => {
    const now = Date.parse("2026-10-02T12:00:00");
    const mk = (id: string, iso: string) => ({ id, title: id, created_at: iso, updated_at: iso, archived_at: null });
    const groups = groupConversations([mk("a", "2026-10-02T09:00:00"), mk("b", "2026-10-01T23:00:00"), mk("c", "2026-09-28T10:00:00"), mk("d", "2026-08-01T10:00:00")], now);
    expect(groups.map((g) => [g.key, g.items.map((i) => i.id)])).toEqual([["Today", ["a"]], ["Yesterday", ["b"]], ["Previous 7 days", ["c"]], ["Older", ["d"]]]);
  });
});
