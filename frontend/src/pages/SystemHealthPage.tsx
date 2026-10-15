import React, { useState } from "react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { apiClient } from "../services/apiClient";
import type { LiveHealthResponse, ReadyHealthResponse, RootHealthResponse } from "../types/api";
import { Activity, Play, CheckCircle2, AlertCircle } from "lucide-react";

export const SystemHealthPage: React.FC = () => {
  const [rootData, setRootData] = useState<RootHealthResponse | null>(null);
  const [liveData, setLiveData] = useState<LiveHealthResponse | null>(null);
  const [readyData, setReadyData] = useState<ReadyHealthResponse | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const testRoot = async () => {
    setLoading("root");
    setErrorMsg(null);
    try {
      const data = await apiClient.getRootHealth();
      setRootData(data);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Root probe failed");
    } finally {
      setLoading(null);
    }
  };

  const testLive = async () => {
    setLoading("live");
    setErrorMsg(null);
    try {
      const data = await apiClient.getLiveHealth();
      setLiveData(data);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Live probe failed");
    } finally {
      setLoading(null);
    }
  };

  const testReady = async () => {
    setLoading("ready");
    setErrorMsg(null);
    try {
      const data = await apiClient.getReadyHealth();
      setReadyData(data);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Ready probe failed");
    } finally {
      setLoading(null);
    }
  };

  const testAll = async () => {
    await Promise.all([testRoot(), testLive(), testReady()]);
  };

  return (
    <div id="system-health-page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>System Probes & Diagnostics</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            Direct interactive verification of FastAPI endpoints, PostgreSQL sockets, and Qdrant readiness.
          </p>
        </div>
        <Button
          id="btn-run-all-probes"
          variant="primary"
          onClick={testAll}
          icon={<Play size={16} />}
        >
          Execute All Health Probes
        </Button>
      </div>

      {errorMsg && (
        <div
          style={{
            padding: "1rem",
            marginBottom: "1.5rem",
            background: "rgba(244, 63, 94, 0.1)",
            border: "1px solid rgba(244, 63, 94, 0.3)",
            borderRadius: "var(--radius-md)",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            color: "var(--accent-rose)",
          }}
        >
          <AlertCircle size={18} />
          <span>{errorMsg}</span>
        </div>
      )}

      <div className="grid-cols-2">
        {/* Liveness Probe Card */}
        <Card
          id="card-liveness-probe"
          title="GET /api/v1/health/live"
          subtitle="Process liveness probe"
          action={
            <Button
              id="btn-probe-live"
              variant="secondary"
              onClick={testLive}
              disabled={loading === "live"}
            >
              Test Live
            </Button>
          }
        >
          {liveData ? (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <CheckCircle2 size={18} color="var(--accent-emerald)" />
                <span style={{ fontWeight: 600 }}>Status: {liveData.status}</span>
                <Badge status="healthy">200 OK</Badge>
              </div>
              <pre
                style={{
                  background: "rgba(0, 0, 0, 0.3)",
                  padding: "0.75rem",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "0.8rem",
                  overflowX: "auto",
                }}
              >
                {JSON.stringify(liveData, null, 2)}
              </pre>
            </div>
          ) : (
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
              Click "Test Live" to trigger the liveness endpoint probe.
            </div>
          )}
        </Card>

        {/* Readiness Probe Card */}
        <Card
          id="card-readiness-probe"
          title="GET /api/v1/health/ready"
          subtitle="Dependency readiness probe"
          action={
            <Button
              id="btn-probe-ready"
              variant="secondary"
              onClick={testReady}
              disabled={loading === "ready"}
            >
              Test Ready
            </Button>
          }
        >
          {readyData ? (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <Badge status={readyData.status}>{readyData.status}</Badge>
                <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                  Env: {readyData.environment} • v{readyData.version}
                </span>
              </div>
              <pre
                style={{
                  background: "rgba(0, 0, 0, 0.3)",
                  padding: "0.75rem",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "0.8rem",
                  overflowX: "auto",
                }}
              >
                {JSON.stringify(readyData, null, 2)}
              </pre>
            </div>
          ) : (
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
              Click "Test Ready" to check PostgreSQL, Qdrant, and FastAPI loop readiness.
            </div>
          )}
        </Card>
      </div>

      {/* Root Health Probe */}
      <Card
        id="card-root-probe"
        title="GET /health"
        subtitle="FastAPI deployment root endpoint with OpenAPI documentation metadata"
        action={
          <Button
            id="btn-probe-root"
            variant="secondary"
            onClick={testRoot}
            disabled={loading === "root"}
          >
            Test Root /health
          </Button>
        }
      >
        {rootData ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <Activity size={18} color="var(--accent-cyan)" />
              <span style={{ fontWeight: 600 }}>Service: {rootData.service}</span>
              <Badge status="healthy">Online</Badge>
            </div>
            <pre
              style={{
                background: "rgba(0, 0, 0, 0.3)",
                padding: "0.75rem",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.8rem",
                overflowX: "auto",
              }}
            >
              {JSON.stringify(rootData, null, 2)}
            </pre>
          </div>
        ) : (
          <div style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
            Click "Test Root /health" to ping root metadata.
          </div>
        )}
      </Card>
    </div>
  );
};
