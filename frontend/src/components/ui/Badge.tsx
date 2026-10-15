import React from "react";
import type { HealthStatus } from "../../types/api";

interface BadgeProps {
  status?: HealthStatus | "neutral" | "info" | "success" | "warning" | "danger";
  children: React.ReactNode;
  id?: string;
}

export const Badge: React.FC<BadgeProps> = ({ status = "neutral", children, id }) => {
  const getBadgeClass = () => {
    switch (status) {
      case "healthy":
      case "success":
        return "badge-healthy";
      case "degraded":
      case "warning":
        return "badge-degraded";
      case "unhealthy":
      case "danger":
        return "badge-unhealthy";
      default:
        return "badge-neutral";
    }
  };

  return (
    <span id={id} className={`badge ${getBadgeClass()}`}>
      {children}
    </span>
  );
};
