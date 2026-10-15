import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";

describe("App Shell and Routing", () => {
  beforeEach(() => {
    // Mock fetch for live and ready probes
    globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/live")) {
        return {
          ok: true,
          headers: new Headers(),
          json: async () => ({
            status: "ok",
            timestamp: new Date().toISOString(),
            uptime_seconds: 120,
          }),
        };
      }
      return {
        ok: true,
        headers: new Headers(),
        json: async () => ({
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
        }),
      };
    });
  });

  it("renders the dashboard sidebar branding and navigation", async () => {
    render(<App />);

    expect(screen.getByText("ContractGuard")).toBeInTheDocument();
    expect(screen.getByText("Multi-Agent Platform")).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Audit Queue")).toBeInTheDocument();
    expect(screen.getByText("System Health")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Contracts Audited")).toBeInTheDocument();
    });
  });

  it("renders metric cards and architecture section on overview", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Contracts Audited")).toBeInTheDocument();
      expect(screen.getByText("High-Risk Flags")).toBeInTheDocument();
      expect(screen.getByText("LangGraph Agents")).toBeInTheDocument();
      expect(screen.getByText("Multi-Agent Pipeline Architecture")).toBeInTheDocument();
    });
  });
});
