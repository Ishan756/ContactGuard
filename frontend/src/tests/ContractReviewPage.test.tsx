import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ContractReviewPage } from "../pages/ContractReviewPage";
import {
  chunkFixture,
  clauseFixture,
  documentFixture,
  workflowFixture,
  workflowResultsFixture,
} from "./fixtures";

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => payload,
  } as Response;
}

describe("ContractReviewPage", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/resume")) {
        return jsonResponse({ ...workflowFixture, status: "awaiting_review" });
      }
      if (url.includes("/workflows/") && url.endsWith("/results")) {
        return jsonResponse(workflowResultsFixture);
      }
      if (url.includes("/workflows/")) {
        return jsonResponse(workflowFixture);
      }
      if (url.includes("/api/v1/workflows")) {
        return jsonResponse({ runs: [workflowFixture], total: 1 });
      }
      if (url.includes("/clauses")) {
        return jsonResponse({ document_id: documentFixture.id, total: 1, clauses: [clauseFixture] });
      }
      if (url.includes("/chunks")) {
        return jsonResponse({
          document_id: documentFixture.id,
          total_chunks: 1,
          page: 1,
          page_size: 100,
          has_more: false,
          chunks: [chunkFixture],
        });
      }
      if (url.includes("/api/v1/documents/")) {
        return jsonResponse(documentFixture);
      }
      if (url.includes("/findings")) {
        return jsonResponse({ document_id: documentFixture.id, total: 1, findings: [workflowResultsFixture.findings[0]] });
      }
      void init;
      return jsonResponse({});
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows review evidence and posts an authenticated reviewer decision", async () => {
    render(
      <MemoryRouter initialEntries={[`/contracts/${documentFixture.id}/review`]}>
        <Routes>
          <Route path="/contracts/:documentId/review" element={<ContractReviewPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText("Reviewer decision")).toBeInTheDocument();
    expect(screen.getByText("Unverified")).toBeInTheDocument();
    expect(screen.getByText("Model-generated explanation")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Submit decision/i }));

    await waitFor(() => {
      expect(screen.getByText(/Decision recorded: approve/i)).toBeInTheDocument();
    });

    const resumeCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) =>
      String(url).endsWith("/resume")
    );
    expect(resumeCall).toBeTruthy();
    const init = resumeCall?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("X-Reviewer-ID")).toBe("local-reviewer");
    expect(JSON.parse(String(init.body))).toMatchObject({
      decision: "approve",
      finding_ids: [workflowResultsFixture.findings[0].finding_id],
    });
  });
});
