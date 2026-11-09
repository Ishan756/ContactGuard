import React from "react";
import { AlertCircle, ChevronLeft, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { Button } from "./Button";

export const PageHeader: React.FC<{
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: React.ReactNode;
  id?: string;
}> = ({ title, description, eyebrow, actions, id }) => (
  <div className="page-header" id={id}>
    <div>
      {eyebrow && <div className="eyebrow">{eyebrow}</div>}
      <h2 className="page-title">{title}</h2>
      {description && <p className="page-description">{description}</p>}
    </div>
    {actions && <div className="page-header-actions">{actions}</div>}
  </div>
);

export const LoadingState: React.FC<{ label?: string; compact?: boolean }> = ({
  label = "Loading…",
  compact = false,
}) => (
  <div className={`state-panel ${compact ? "state-panel-compact" : ""}`} role="status" aria-live="polite">
    <Loader2 className="spin" size={compact ? 18 : 28} aria-hidden="true" />
    <span>{label}</span>
  </div>
);

export const ErrorState: React.FC<{
  message: string;
  onRetry?: () => void;
  compact?: boolean;
  title?: string;
}> = ({ message, onRetry, compact = false, title = "Something went wrong" }) => (
  <div className={`state-panel state-panel-error ${compact ? "state-panel-compact" : ""}`} role="alert">
    <AlertCircle size={compact ? 18 : 28} aria-hidden="true" />
    <div>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
    {onRetry && (
      <Button variant="secondary" onClick={onRetry} icon={<RefreshCw size={14} />}>
        Retry
      </Button>
    )}
  </div>
);

export const EmptyState: React.FC<{
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}> = ({ title, description, icon, action }) => (
  <div className="empty-state">
    {icon && <div className="empty-state-icon">{icon}</div>}
    <h3>{title}</h3>
    {description && <p>{description}</p>}
    {action}
  </div>
);

export const ProgressBar: React.FC<{
  value?: number | null;
  label?: string;
  indeterminate?: boolean;
  tone?: "cyan" | "emerald" | "amber" | "rose";
}> = ({ value, label, indeterminate = false, tone = "cyan" }) => {
  const clamped = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="progress-block">
      {label && (
        <div className="progress-label">
          <span>{label}</span>
          {!indeterminate && <span>{Math.round(clamped)}%</span>}
        </div>
      )}
      <div
        className={`progress-track ${indeterminate ? "progress-indeterminate" : ""}`}
        role="progressbar"
        aria-label={label || "Progress"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : Math.round(clamped)}
      >
        <div className={`progress-fill progress-${tone}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
};

export const Pagination: React.FC<{
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  label?: string;
}> = ({ page, pageSize, total, onPageChange, label = "items" }) => {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  return (
    <div className="pagination" aria-label="Pagination">
      <span className="pagination-summary">
        {start}–{end} of {total} {label}
      </span>
      <div className="pagination-controls">
        <button
          type="button"
          className="icon-button"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft size={16} />
        </button>
        <span className="pagination-page">
          Page {page} of {pages}
        </span>
        <button
          type="button"
          className="icon-button"
          aria-label="Next page"
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};

export const Notice: React.FC<{
  tone?: "info" | "warning" | "danger" | "success";
  children: React.ReactNode;
  title?: string;
}> = ({ tone = "info", children, title }) => (
  <div className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : "status"}>
    <div>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  </div>
);
