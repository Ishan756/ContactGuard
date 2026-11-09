import type {
  ReviewDecisionType,
  ReviewStatus,
  RiskPriority,
  ValidationStatus,
  WorkflowStatus,
} from "../types/api";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "violet";

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
    ["second", 1],
  ];
  for (const [unit, seconds] of units) {
    if (Math.abs(diffSeconds) >= seconds || unit === "second") {
      return formatter.format(Math.round(diffSeconds / seconds), unit);
    }
  }
  return "just now";
}

export function formatBytes(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
}

export function titleCase(value?: string | null): string {
  if (!value) return "—";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

export const severityOrder: Record<RiskPriority, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
};

export function severityTone(severity: RiskPriority): Tone {
  switch (severity) {
    case "critical":
    case "high":
      return "danger";
    case "medium":
      return "warning";
    case "low":
      return "info";
    default:
      return "neutral";
  }
}

export function validationTone(status: ValidationStatus): Tone {
  switch (status) {
    case "verified":
      return "success";
    case "unverified":
      return "danger";
    case "needs_review":
    case "missing_evidence":
    case "inconclusive":
      return "warning";
    default:
      return "neutral";
  }
}

export function reviewTone(status: ReviewStatus): Tone {
  switch (status) {
    case "reviewed":
      return "success";
    case "dismissed":
      return "neutral";
    default:
      return "warning";
  }
}

export function workflowTone(status: WorkflowStatus): Tone {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
    case "cancelled":
      return "danger";
    case "awaiting_review":
      return "warning";
    case "running":
    case "revising":
      return "info";
    default:
      return "neutral";
  }
}

export function decisionTone(decision: ReviewDecisionType): Tone {
  switch (decision) {
    case "approve":
      return "success";
    case "dismiss":
      return "neutral";
    default:
      return "warning";
  }
}

export function validationLabel(status: ValidationStatus): string {
  switch (status) {
    case "verified":
      return "Verified";
    case "unverified":
      return "Unverified";
    case "needs_review":
      return "Needs review";
    case "missing_evidence":
      return "Missing evidence";
    case "inconclusive":
      return "Inconclusive";
    default:
      return "Pending validation";
  }
}

export function workflowStatusLabel(status: WorkflowStatus): string {
  switch (status) {
    case "awaiting_review":
      return "Awaiting human review";
    case "revising":
      return "Revising";
    default:
      return titleCase(status);
  }
}

export function sourcePage(reference?: string | null, page?: number | null): number | null {
  if (page && page > 0) return page;
  if (!reference) return null;
  const pageMatch = reference.match(/(?:page|p)[:=_-]?\s*(\d+)/i);
  if (pageMatch) return Number(pageMatch[1]);
  return null;
}
