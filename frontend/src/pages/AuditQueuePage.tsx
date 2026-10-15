import React from "react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { FileUp, Info } from "lucide-react";

export const AuditQueuePage: React.FC = () => {
  return (
    <div id="audit-queue-page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Contract Audit Queue</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            Monitor and review AI-driven multi-agent contract risk assessments.
          </p>
        </div>
        <Button
          id="btn-upload-contract-placeholder"
          variant="primary"
          icon={<FileUp size={16} />}
          onClick={() => alert("Contract ingestion pipeline will be wired in Prompt 2.")}
        >
          Upload New Agreement
        </Button>
      </div>

      <Card id="audit-queue-table-card">
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" id="audit-contracts-table">
            <thead>
              <tr>
                <th>Contract Name</th>
                <th>Format</th>
                <th>Agents Assigned</th>
                <th>Risk Score</th>
                <th>Status</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ fontWeight: 600 }}>Master Services Agreement (MSA) - Enterprise</td>
                <td><Badge status="neutral">PDF</Badge></td>
                <td>Legal, Compliance, Financial</td>
                <td><Badge status="warning">Awaiting Audit</Badge></td>
                <td><span className="status-dot degraded" style={{ marginRight: "0.5rem" }} />Queued</td>
                <td style={{ color: "var(--text-muted)" }}>Just now</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Non-Disclosure Agreement (NDA) - Bilateral</td>
                <td><Badge status="neutral">DOCX</Badge></td>
                <td>Legal, Compliance</td>
                <td><Badge status="warning">Awaiting Audit</Badge></td>
                <td><span className="status-dot degraded" style={{ marginRight: "0.5rem" }} />Queued</td>
                <td style={{ color: "var(--text-muted)" }}>10m ago</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          style={{
            marginTop: "1.5rem",
            padding: "1rem",
            background: "rgba(6, 182, 212, 0.05)",
            borderRadius: "var(--radius-md)",
            border: "1px solid rgba(6, 182, 212, 0.2)",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <Info size={20} color="var(--accent-cyan)" />
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            <strong>Foundation Stage:</strong> Ingestion and multi-agent workflow nodes are reserved for Prompt 2.
            This queue shell is fully wired to the design system and ready for live socket updates.
          </p>
        </div>
      </Card>
    </div>
  );
};
