import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VersionComparisonPage } from "../pages/VersionComparisonPage";
import { comparisonFixture, documentFixture } from "./fixtures";
import type { DocumentMetadataResponse } from "../types/api";

const targetDocument: DocumentMetadataResponse = {
  ...documentFixture,
  id: comparisonFixture.target_document_id,
  original_filename: "acme-vendor-agreement-v2.pdf",
};

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  } as Response;
}

describe("VersionComparisonPage", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/v1/documents")) {
          return jsonResponse({ documents: [documentFixture, targetDocument], total: 2 });
        }
        if (url.includes("/api/v1/comparisons")) {
          if (init?.method === "POST") {
            return jsonResponse(comparisonFixture, 201);
          }
          return jsonResponse({ comparisons: [comparisonFixture], total: 1 });
        }
        return jsonResponse({});
      }
    );
  });

  it("renders stored comparison changes and finding-level differences", async () => {
    render(<VersionComparisonPage />);

    await waitFor(() => {
      expect(screen.getByText("Recent comparisons")).toBeInTheDocument();
    });

    expect(screen.getByText("Liability cap period changed from twelve months to six months.")).toBeInTheDocument();
    expect(screen.getByText("The liability cap deviation increased in review priority.")).toBeInTheDocument();
    expect(screen.getByText("Severity")).toBeInTheDocument();
    expect(screen.getByText("Not run")).toBeInTheDocument();
    expect(
      screen.getByText(/Version comparison identifies textual and finding-level changes/)
    ).toBeInTheDocument();
  });

  it("submits a comparison with reviewer authentication", async () => {
    render(<VersionComparisonPage />);

    await waitFor(() => {
      expect(screen.getByLabelText("Earlier version")).toHaveValue(documentFixture.id);
      expect(screen.getByLabelText("Newer version")).toHaveValue(targetDocument.id);
    });

    fireEvent.click(screen.getByRole("button", { name: /compare versions/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/comparisons"),
        expect.objectContaining({ method: "POST" })
      );
    });

    const postCall = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(([, init]) => init?.method === "POST");
    const headers = new Headers(postCall?.[1]?.headers);
    expect(headers.get("X-Reviewer-ID")).toBeTruthy();
    expect(headers.get("X-Workflow-Key")).toBeTruthy();
    expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({
      base_document_id: documentFixture.id,
      target_document_id: targetDocument.id,
      reanalyze_target: false,
    });
  });
});
