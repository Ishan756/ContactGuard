import React from "react";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Shield, Server, Cpu } from "lucide-react";

export const SettingsPage: React.FC = () => {
  return (
    <div id="settings-page">
      <div style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Platform Configuration</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
          Environment settings and integration configurations (configured via <code>.env</code>).
        </p>
      </div>

      <div className="grid-cols-2">
        <Card id="card-settings-api" title="Backend & Server" subtitle="FastAPI runtime options">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-secondary)" }}>Application</span>
              <span style={{ fontWeight: 600 }}>ContractGuard Backend</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-secondary)" }}>API Host & Port</span>
              <code>0.0.0.0:8000</code>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-secondary)" }}>CORS Whitelist</span>
              <Badge status="neutral">localhost:5173, localhost:3000</Badge>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0" }}>
              <span style={{ color: "var(--text-secondary)" }}>Swagger Docs</span>
              <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" style={{ color: "var(--accent-cyan)", textDecoration: "none" }}>
                /docs
              </a>
            </div>
          </div>
        </Card>

        <Card id="card-settings-ai" title="AI & Vector Subsystems" subtitle="Gemini and Qdrant integration">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-secondary)" }}>LLM Provider</span>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Cpu size={16} color="var(--accent-violet)" />
                <span style={{ fontWeight: 600 }}>Gemini API (Abstraction Layer)</span>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-secondary)" }}>Default Model</span>
              <code>gemini-1.5-pro</code>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-secondary)" }}>Vector Storage</span>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Server size={16} color="var(--accent-emerald)" />
                <span>Qdrant (localhost:6333)</span>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0" }}>
              <span style={{ color: "var(--text-secondary)" }}>Security Secrets</span>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Shield size={16} color="var(--accent-cyan)" />
                <span style={{ fontSize: "0.85rem", color: "var(--accent-emerald)" }}>Protected (.env)</span>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
