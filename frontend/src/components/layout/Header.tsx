import React, { useEffect, useState } from "react";
import { apiClient } from "../../services/apiClient";
import type { LiveHealthResponse } from "../../types/api";

interface HeaderProps {
  title: string;
}

export const Header: React.FC<HeaderProps> = ({ title }) => {
  const [liveStatus, setLiveStatus] = useState<LiveHealthResponse | null>(null);
  const [isChecking, setIsChecking] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;

    const checkLive = async () => {
      try {
        const resp = await apiClient.getLiveHealth();
        if (mounted) {
          setLiveStatus(resp);
          setIsChecking(false);
        }
      } catch {
        if (mounted) {
          setLiveStatus(null);
          setIsChecking(false);
        }
      }
    };

    checkLive();
    const interval = setInterval(checkLive, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="topbar" id="header-topbar">
      <div>
        <h1 style={{ fontSize: "1.35rem", fontWeight: 700 }}>{title}</h1>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <div
          id="api-health-status-badge"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            fontSize: "0.85rem",
            padding: "0.35rem 0.75rem",
            background: "rgba(255, 255, 255, 0.04)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <span
            className={`status-dot ${
              isChecking ? "degraded" : liveStatus?.status === "ok" ? "healthy" : "unhealthy"
            }`}
          />
          <span style={{ color: "var(--text-secondary)" }}>
            {isChecking
              ? "Checking API..."
              : liveStatus?.status === "ok"
              ? `FastAPI Live (${liveStatus.uptime_seconds.toFixed(0)}s)`
              : "API Disconnected"}
          </span>
        </div>
      </div>
    </header>
  );
};
