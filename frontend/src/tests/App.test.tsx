import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { evaluationSummaryFixture } from "./fixtures";

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => payload,
  } as Response;
}

describe("App Shell and Routing", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/live")) {
        return jsonResponse({
          status: "ok",
          timestamp: new Date().toISOString(),
          uptime_seconds: 120,
        });
      }
      if (url.includes("/health/ready")) {
        return jsonResponse({
          status: "healthy",
          app: "ContractGuard",
          version: "0.1.0",
          environment: "development",
          timestamp: new Date().toISOString(),
          components: {
            api: { status: "healthy", details: "Core active", latency_ms: 0.1 },
            vector_db_qdrant: { status: "healthy", details: "Connected", latency_ms: 1.2 },
            relational_db_postgres: { status: "healthy", details: "Connected", latency_ms: 0.8 },
          },
        });
      }
      if (url.includes("/api/v1/evaluation/summary")) {
        return jsonResponse(evaluationSummaryFixture);
      }
      if (url.includes("/api/v1/workflows")) {
        return jsonResponse({ runs: [], total: 0 });
      }
      if (url.includes("/api/v1/documents")) {
        return jsonResponse({ documents: [], total: 0 });
      }
      return jsonResponse({});
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the workspace branding and primary navigation", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Uploaded contracts")).toBeInTheDocument();
    });

    expect(screen.getByText("ContractGuard")).toBeInTheDocument();
    expect(screen.getByText("Contract evidence review")).toBeInTheDocument();
    expect(document.getElementById("nav-overview")).toHaveTextContent("Overview");
    expect(document.getElementById("nav-upload")).toHaveTextContent("Upload contracts");
    expect(document.getElementById("nav-findings")).toHaveTextContent("Findings");
    expect(document.getElementById("nav-history")).toHaveTextContent("Review history");
    expect(document.getElementById("nav-comparisons")).toHaveTextContent("Version comparison");
    expect(document.getElementById("nav-policies")).toHaveTextContent("Policy library");
    expect(document.getElementById("nav-health")).toHaveTextContent("System health");
    expect(document.getElementById("nav-settings")).toHaveTextContent("Settings");
  });

  it("renders empty dashboard states from real API response shapes", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("No findings yet")).toBeInTheDocument();
      expect(screen.getByText("No workflow runs")).toBeInTheDocument();
      expect(screen.getByText("No contracts uploaded")).toBeInTheDocument();
    });
  });

  it("renders the evaluation benchmark summary with computed metrics", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Evaluation benchmark")).toBeInTheDocument();
    });

    expect(screen.getByText("Single-LLM baseline")).toBeInTheDocument();
    expect(screen.getByText("Multi-agent workflow")).toBeInTheDocument();
    expect(screen.getByText("Finding precision")).toBeInTheDocument();
    expect(screen.getByText("Citation validity")).toBeInTheDocument();
    expect(screen.getByText("Deterministic mock")).toBeInTheDocument();
    expect(
      screen.getByText(/do not establish legal correctness/)
    ).toBeInTheDocument();
  });
});
