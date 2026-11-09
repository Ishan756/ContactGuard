import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Settings as SettingsIcon, UserRound } from "lucide-react";
import { apiClient } from "../../services/apiClient";
import { getReviewerAuth, subscribeReviewerAuth } from "../../services/session";
import type { LiveHealthResponse } from "../../types/api";

interface HeaderProps {
  title: string;
}

export const Header: React.FC<HeaderProps> = ({ title }) => {
  const [liveStatus, setLiveStatus] = useState<LiveHealthResponse | null>(null);
  const [isChecking, setIsChecking] = useState<boolean>(true);
  const [reviewerId, setReviewerId] = useState<string | null>(getReviewerAuth()?.reviewerId || null);

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

    void checkLive();
    const interval = setInterval(checkLive, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    return subscribeReviewerAuth(() => {
      setReviewerId(getReviewerAuth()?.reviewerId || null);
    });
  }, []);

  const online = liveStatus?.status === "ok";

  return (
    <header className="topbar" id="header-topbar">
      <div>
        <h1 className="topbar-title">{title}</h1>
      </div>

      <div className="topbar-actions">
        <div id="api-health-status-badge" className="health-pill" role="status">
          <span className={`status-dot ${isChecking ? "degraded" : online ? "healthy" : "unhealthy"}`} />
          <span>
            {isChecking
              ? "Checking API…"
              : online
                ? `API live${liveStatus?.uptime_seconds != null ? ` · ${Math.round(liveStatus.uptime_seconds)}s` : ""}`
                : "API disconnected"}
          </span>
        </div>
        <Link className="reviewer-pill" to="/settings" title="Reviewer settings">
          <UserRound size={15} />
          <span>{reviewerId || "No reviewer"}</span>
          <SettingsIcon size={13} />
        </Link>
      </div>
    </header>
  );
};
