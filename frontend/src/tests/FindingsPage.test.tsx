import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { FindingsPage } from "../pages/FindingsPage";
import { documentFixture, findingFixture } from "./fixtures";

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => payload,
  } as Response;
}

describe("FindingsPage", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/findings")) {
        return jsonResponse({ document_id: documentFixture.id, total: 1, findings: [findingFixture] });
      }
      if (url.includes("/api/v1/documents")) {
        return jsonResponse({ documents: [documentFixture], total: 1 });
      }
      return jsonResponse({});
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders finding evidence with explicit unverified and model labels", async () => {
    render(
      <MemoryRouter>
        <FindingsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/aggregate liability shall not exceed/i)).toBeInTheDocument();
    });

    expect(screen.getByText("Unverified")).toBeInTheDocument();
    expect(screen.getByText("Model-generated explanation")).toBeInTheDocument();
    expect(screen.getByText(/annual contract value is not yet known/i)).toBeInTheDocument();
    expect(screen.getByText("Contract page 2")).toBeInTheDocument();

    const detailsLink = screen.getByRole("link", { name: /View finding details/i });
    expect(detailsLink).toHaveAttribute(
      "href",
      `/findings/${documentFixture.id}/${findingFixture.finding_id}`
    );
  });

  it("filters findings by validation status", async () => {
    const { container } = render(
      <MemoryRouter>
        <FindingsPage />
      </MemoryRouter>
    );

    await screen.findByText("Unverified");
    const validationSelect = container.querySelectorAll("select")[2] as HTMLSelectElement;
    validationSelect.value = "verified";
    validationSelect.dispatchEvent(new Event("change", { bubbles: true }));

    await waitFor(() => {
      expect(screen.getByText("No findings match these filters")).toBeInTheDocument();
    });
  });
});
