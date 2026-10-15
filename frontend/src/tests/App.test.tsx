import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "../App";

describe("App Shell and Routing", () => {
  beforeEach(() => {
    // Mock fetch for health probes
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({
        status: "ok",
        app: "ContractGuard",
        version: "0.1.0",
        environment: "development",
        timestamp: new Date().toISOString(),
        components: {
          api: { status: "healthy", details: "Core active" },
          vector_db_qdrant: { status: "healthy", details: "Connected" },
          relational_db_postgres: { status: "healthy", details: "Connected" },
        },
      }),
    });
  });

  it("renders the dashboard sidebar branding and navigation", () => {
    render(<App />);

    expect(screen.getByText("ContractGuard")).toBeInTheDocument();
    expect(screen.getByText("Multi-Agent Platform")).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Audit Queue")).toBeInTheDocument();
    expect(screen.getByText("System Health")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders metric cards and architecture section on overview", () => {
    render(<App />);

    expect(screen.getByText("Contracts Audited")).toBeInTheDocument();
    expect(screen.getByText("High-Risk Flags")).toBeInTheDocument();
    expect(screen.getByText("LangGraph Agents")).toBeInTheDocument();
    expect(screen.getByText("Multi-Agent Pipeline Architecture")).toBeInTheDocument();
  });
});
