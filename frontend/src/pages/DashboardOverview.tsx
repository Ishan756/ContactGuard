import React, { useEffect, useState } from "react";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { apiClient } from "../services/apiClient";
import type { ReadyHealthResponse } from "../types/api";
import {
  FileText,
  AlertTriangle,
  Bot,
  Zap,
  ArrowRight,
  RefreshCw,
  Cpu,
  Layers,
  Database,
} from "lucide-react";

export const DashboardOverview: React.FC = () => {
  const [health, setHealth] = useState<ReadyHealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchHealth = async () => {
    setIsLoading(true);
    try {
      const resp = await apiClient.getReadyHealth();
      setHealth(resp);
    } catch {
      setHealth(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  return (
    <div id="dashboard-overview-page">
      {/* Metric Cards Row */}
      <div className="grid-cols-4">
        <Card id="stat-total-contracts">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.85rem", fontWeight: 500 }}>
              Contracts Audited
            </span>
            <div style={{ padding: "0.4rem", borderRadius: "var(--radius-sm)", background: "rgba(6, 182, 212, 0.15)" }}>
              <FileText size={18} color="var(--accent-cyan)" />
            </div>
          </div>
          <div style={{ fontSize: "1.85rem", fontWeight: 700, marginTop: "0.5rem" }}>0</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Foundation ready for ingestion
          </div>
        </Card>

        <Card id="stat-high-risks">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.85rem", fontWeight: 500 }}>
              High-Risk Flags
            </span>
            <div style={{ padding: "0.4rem", borderRadius: "var(--radius-sm)", background: "rgba(244, 63, 94, 0.15)" }}>
              <AlertTriangle size={18} color="var(--accent-rose)" />
            </div>
          </div>
          <div style={{ fontSize: "1.85rem", fontWeight: 700, marginTop: "0.5rem" }}>0</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Clause risk rules initialized
          </div>
        </Card>

        <Card id="stat-agents">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.85rem", fontWeight: 500 }}>
              LangGraph Agents
            </span>
            <div style={{ padding: "0.4rem", borderRadius: "var(--radius-sm)", background: "rgba(139, 92, 246, 0.15)" }}>
              <Bot size={18} color="var(--accent-violet)" />
            </div>
          </div>
          <div style={{ fontSize: "1.85rem", fontWeight: 700, marginTop: "0.5rem" }}>3</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Legal, Financial & Compliance
          </div>
        </Card>

        <Card id="stat-system-status">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.85rem", fontWeight: 500 }}>
              System Readiness
            </span>
            <div style={{ padding: "0.4rem", borderRadius: "var(--radius-sm)", background: "rgba(16, 185, 129, 0.15)" }}>
              <Zap size={18} color="var(--accent-emerald)" />
            </div>
          </div>
          <div style={{ marginTop: "0.5rem" }}>
            <Badge status={health?.status === "healthy" ? "healthy" : "warning"}>
              {health?.status || "Checking..."}
            </Badge>
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
            Backend API online
          </div>
        </Card>
      </div>

      {/* Main Grid: Multi-Agent Architecture & Quick Probe */}
      <div className="grid-cols-2">
        <Card
          id="architecture-overview-card"
          title="Multi-Agent Pipeline Architecture"
          subtitle="ContractGuard Orchestration Framework"
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
              <div style={{ padding: "0.5rem", borderRadius: "var(--radius-md)", background: "rgba(6, 182, 212, 0.1)" }}>
                <Layers size={20} color="var(--accent-cyan)" />
              </div>
              <div>
                <h4 style={{ fontSize: "0.95rem", fontWeight: 600 }}>1. Ingestion & Document Parsing</h4>
                <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                  PyMuPDF and python-docx parse incoming agreements, chunking clauses with semantic boundary detection.
                </p>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
              <div style={{ padding: "0.5rem", borderRadius: "var(--radius-md)", background: "rgba(139, 92, 246, 0.1)" }}>
                <Cpu size={20} color="var(--accent-violet)" />
              </div>
              <div>
                <h4 style={{ fontSize: "0.95rem", fontWeight: 600 }}>2. LangGraph Multi-Agent Audit</h4>
                <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                  Specialized agents (Compliance, Liability, Financial Exposure) critique clauses concurrently via Gemini.
                </p>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
              <div style={{ padding: "0.5rem", borderRadius: "var(--radius-md)", background: "rgba(16, 185, 129, 0.1)" }}>
                <Database size={20} color="var(--accent-emerald)" />
              </div>
              <div>
                <h4 style={{ fontSize: "0.95rem", fontWeight: 600 }}>3. Vector Indexing & Synthesis</h4>
                <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                  Clauses stored in Qdrant with risk scores and recommendations persisted in PostgreSQL.
                </p>
              </div>
            </div>
          </div>
        </Card>

        <Card
          id="system-probe-card"
          title="Subsystem Health Probes"
          subtitle="Real-time monitoring from /api/v1/health/ready"
          action={
            <Button
              id="btn-refresh-health"
              variant="secondary"
              onClick={fetchHealth}
              disabled={isLoading}
              icon={<RefreshCw size={14} className={isLoading ? "spin" : ""} />}
            >
              Refresh
            </Button>
          }
        >
          {health ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {Object.entries(health.components).map(([name, comp]) => (
                <div
                  key={name}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.75rem",
                    borderRadius: "var(--radius-md)",
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem", textTransform: "capitalize" }}>
                      {name.replace(/_/g, " ")}
                    </div>
                    {comp.details && (
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                        {comp.details}
                      </div>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    {comp.latency_ms !== undefined && comp.latency_ms !== null && (
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {comp.latency_ms.toFixed(1)}ms
                      </span>
                    )}
                    <Badge status={comp.status}>{comp.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
              {isLoading ? "Querying health probes..." : "Unable to reach backend API. Ensure backend is running."}
            </div>
          )}
        </Card>
      </div>

      {/* Contract Auditing Pipeline Queue Card */}
      <Card
        id="quick-start-card"
        title="Audit Pipeline Ready"
        subtitle="Monorepo foundation successfully initialized"
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
              The backend FastAPI service and React Vite frontend are fully scaffolded with structured logging,
              request tracing, and environment-driven configurations.
            </p>
          </div>
          <Button
            id="btn-view-queue"
            variant="primary"
            onClick={() => window.location.href = "/audits"}
            icon={<ArrowRight size={16} />}
          >
            Open Audit Queue
          </Button>
        </div>
      </Card>
    </div>
  );
};
