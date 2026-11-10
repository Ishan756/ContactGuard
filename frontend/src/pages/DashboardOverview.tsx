import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileSearch,
  FileText,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { ToneBadge, WorkflowStatusBadge } from "../components/ui/StatusBadge";
import { EmptyState, ErrorState, LoadingState, Notice, PageHeader } from "../components/ui/States";
import { apiClient, ApiClientError } from "../services/apiClient";
import { getReviewerAuth } from "../services/session";
import type {
  DocumentMetadataResponse,
  EvaluationSummaryResponse,
  RiskPriority,
  WorkflowRunResponse,
  WorkflowStatus,
} from "../types/api";
import {
  formatBytes,
  formatDate,
  formatRelative,
  severityTone,
  titleCase,
} from "../utils/format";

const severityKeys: RiskPriority[] = ["critical", "high", "medium", "low", "informational"];
const evaluationMetricKeys = [
  "precision",
  "recall",
  "f1",
  "citation_validity",
  "unsupported_claim_rate",
] as const;

const evaluationMetricLabels: Record<(typeof evaluationMetricKeys)[number], string> = {
  precision: "Finding precision",
  recall: "Finding recall",
  f1: "F1 score",
  citation_validity: "Citation validity",
  unsupported_claim_rate: "Unsupported legal claims",
};

function numericMetric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

const workflowKeys: WorkflowStatus[] = [
  "awaiting_review",
  "running",
  "completed",
  "failed",
  "pending",
  "revising",
  "cancelled",
];

export const DashboardOverview: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentMetadataResponse[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowRunResponse[]>([]);
  const [documentTotal, setDocumentTotal] = useState(0);
  const [workflowTotal, setWorkflowTotal] = useState(0);
  const [evaluation, setEvaluation] = useState<EvaluationSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setWorkflowError(null);
    const [documentsResult, workflowsResult, evaluationResult] = await Promise.allSettled([
      apiClient.listDocuments(12, 0),
      apiClient.listWorkflows({ limit: 30 }),
      apiClient.getEvaluationSummary(),
    ]);

    if (documentsResult.status === "fulfilled") {
      setDocuments(documentsResult.value.documents);
      setDocumentTotal(documentsResult.value.total);
    } else {
      setError(
        documentsResult.reason instanceof Error
          ? documentsResult.reason.message
          : "Unable to load contracts."
      );
    }

    if (workflowsResult.status === "fulfilled") {
      setWorkflows(workflowsResult.value.runs);
      setWorkflowTotal(workflowsResult.value.total);
    } else {
      setWorkflows([]);
      setWorkflowTotal(0);
      setWorkflowError(
        workflowsResult.reason instanceof ApiClientError
          ? workflowsResult.reason.message
          : "Unable to load workflow runs."
      );
    }

    if (evaluationResult.status === "fulfilled") {
      setEvaluation(evaluationResult.value);
    } else {
      setEvaluation(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const findings = useMemo(
    () => workflows.flatMap((workflow) => workflow.review_report?.findings ?? []),
    [workflows]
  );

  const severityCounts = useMemo(() => {
    const counts = Object.fromEntries(severityKeys.map((key) => [key, 0])) as Record<
      RiskPriority,
      number
    >;
    findings.forEach((finding) => {
      counts[finding.severity] = (counts[finding.severity] || 0) + 1;
    });
    return counts;
  }, [findings]);

  const totalFindings = findings.length;
  const highRisk = severityCounts.critical + severityCounts.high;
  const awaitingReview = workflows.filter((run) => run.status === "awaiting_review").length;
  const verified = findings.filter((finding) => finding.validation_status === "verified").length;

  const workflowCounts = useMemo(() => {
    const counts = Object.fromEntries(workflowKeys.map((key) => [key, 0])) as Record<
      WorkflowStatus,
      number
    >;
    workflows.forEach((run) => {
      counts[run.status] = (counts[run.status] || 0) + 1;
    });
    return counts;
  }, [workflows]);

  const recentRuns = workflows.slice(0, 6);
  const recentDocuments = documents.slice(0, 6);
  const auth = getReviewerAuth();

  const evaluationRows = useMemo(() => {
    if (!evaluation?.available) return [];
    const baseline = evaluation.agents.baseline?.findings ?? {};
    const multiAgent = evaluation.agents.multi_agent?.findings ?? {};
    return evaluationMetricKeys.map((key) => {
      const baselineValue = numericMetric(baseline[key]);
      const multiAgentValue = numericMetric(multiAgent[key]);
      return {
        key,
        label: evaluationMetricLabels[key],
        baseline: baselineValue,
        multiAgent: multiAgentValue,
        delta:
          baselineValue !== null && multiAgentValue !== null
            ? multiAgentValue - baselineValue
            : null,
      };
    });
  }, [evaluation]);

  if (loading) {
    return <LoadingState label="Loading dashboard…" />;
  }

  if (error && documents.length === 0) {
    return <ErrorState title="Dashboard unavailable" message={error} onRetry={load} />;
  }

  return (
    <div id="dashboard-overview-page">
      <PageHeader
        eyebrow="Review operations"
        title="Contract intelligence dashboard"
        description="Track uploaded agreements, automated evidence verification, and human review queues across the workspace."
        actions={
          <>
            <Link className="btn btn-secondary" to="/history">
              Review history
            </Link>
            <Link className="btn btn-primary" to="/upload">
              <Upload size={16} /> Upload contract
            </Link>
          </>
        }
      />

      {!auth && (
        <Notice tone="warning" title="Reviewer credentials required">
          Configure a reviewer ID and workflow API key in <Link to="/settings">Settings</Link> to
          start runs and action review queues.
        </Notice>
      )}
      {workflowError && (
        <Notice tone={auth ? "danger" : "warning"} title="Workflow data unavailable">
          {workflowError}
        </Notice>
      )}

      <div className="stat-grid">
        <Card id="stat-total-contracts">
          <div className="stat-card">
            <div>
              <span className="stat-label">Uploaded contracts</span>
              <div className="stat-value">{documentTotal}</div>
              <span className="stat-note">Secure PDF and DOCX ingestion</span>
            </div>
            <span className="stat-icon stat-icon-cyan"><FileText size={20} /></span>
          </div>
        </Card>
        <Card id="stat-awaiting-review">
          <div className="stat-card">
            <div>
              <span className="stat-label">Awaiting review</span>
              <div className="stat-value">{awaitingReview}</div>
              <span className="stat-note">Human decisions pending</span>
            </div>
            <span className="stat-icon stat-icon-amber"><Clock3 size={20} /></span>
          </div>
        </Card>
        <Card id="stat-high-risks">
          <div className="stat-card">
            <div>
              <span className="stat-label">High-risk findings</span>
              <div className="stat-value">{highRisk}</div>
              <span className="stat-note">Critical and high priority</span>
            </div>
            <span className="stat-icon stat-icon-rose"><AlertTriangle size={20} /></span>
          </div>
        </Card>
        <Card id="stat-verified">
          <div className="stat-card">
            <div>
              <span className="stat-label">Verified evidence</span>
              <div className="stat-value">{verified}</div>
              <span className="stat-note">{totalFindings} findings across recent runs</span>
            </div>
            <span className="stat-icon stat-icon-emerald"><ShieldCheck size={20} /></span>
          </div>
        </Card>
      </div>

      <div className="dashboard-grid">
        <Card
          title="Risk distribution"
          subtitle="Severity across findings from recent workflow reports"
          action={
            <Button variant="secondary" onClick={load} icon={<RefreshCw size={14} />}>
              Refresh
            </Button>
          }
        >
          {totalFindings === 0 ? (
            <EmptyState
              icon={<FileSearch size={26} />}
              title="No findings yet"
              description="Start a review workflow on an uploaded contract to populate risk distribution."
              action={<Link className="text-link" to="/upload">Upload a contract →</Link>}
            />
          ) : (
            <div className="distribution-list">
              {severityKeys.map((severity) => {
                const count = severityCounts[severity];
                const percent = totalFindings ? (count / totalFindings) * 100 : 0;
                return (
                  <div className="distribution-row" key={severity}>
                    <div className="distribution-label">
                      <ToneBadge tone={severityTone(severity)}>{severity}</ToneBadge>
                      <span>{count}</span>
                    </div>
                    <div className="distribution-track">
                      <div
                        className={`distribution-fill severity-fill-${severity}`}
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card title="Workflow status" subtitle={`${workflowTotal} workflow runs tracked`}>
          {workflows.length === 0 ? (
            <EmptyState
              icon={<Clock3 size={26} />}
              title="No workflow runs"
              description="Runs appear here after a contract review is started."
            />
          ) : (
            <div className="status-grid">
              {workflowKeys
                .filter((status) => workflowCounts[status] > 0)
                .map((status) => (
                  <div className="status-tile" key={status}>
                    <WorkflowStatusBadge status={status} />
                    <strong>{workflowCounts[status]}</strong>
                  </div>
                ))}
            </div>
          )}
          <div className="card-divider" />
          <div className="insight-row">
            <CheckCircle2 size={16} />
            <span>
              Automatic verification completed for{" "}
              {workflows.filter((run) => run.validation_run_id).length} recent runs.
            </span>
          </div>
        </Card>
      </div>

      <Card
        className="evaluation-card"
        title="Evaluation benchmark"
        subtitle="Versioned synthetic benchmark comparing the single-LLM baseline with the multi-agent workflow"
        action={
          evaluation?.available ? (
            <ToneBadge tone={evaluation.mode === "live" ? "warning" : "info"}>
              {evaluation.mode === "live" ? "Live model run" : "Deterministic mock"}
            </ToneBadge>
          ) : undefined
        }
      >
        {!evaluation?.available ? (
          <EmptyState
            icon={<BarChart3 size={26} />}
            title="Evaluation summary unavailable"
            description={
              evaluation?.reason ||
              "Run the evaluation benchmark CLI to generate a versioned report."
            }
          />
        ) : (
          <>
            <div className="evaluation-meta">
              <span>
                Dataset <strong>{evaluation.dataset_version || "unknown"}</strong> ·{" "}
                {evaluation.benchmark.contracts} contracts ·{" "}
                {evaluation.benchmark.ground_truth_findings} annotated findings
              </span>
              <span>
                Generated {formatDate(evaluation.generated_at)} · mode{" "}
                {evaluation.mode || "unknown"}
              </span>
            </div>
            <div className="table-wrap">
              <table className="data-table evaluation-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Single-LLM baseline</th>
                    <th>Multi-agent workflow</th>
                    <th>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {evaluationRows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td>{row.baseline === null ? "—" : row.baseline.toFixed(4)}</td>
                      <td>
                        {row.multiAgent === null ? "—" : row.multiAgent.toFixed(4)}
                      </td>
                      <td
                        className={
                          row.delta === null
                            ? ""
                            : row.delta > 0
                              ? "metric-positive"
                              : row.delta < 0
                                ? "metric-negative"
                                : ""
                        }
                      >
                        {row.delta === null
                          ? "—"
                          : `${row.delta > 0 ? "+" : ""}${row.delta.toFixed(4)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card-divider" />
            <div className="insight-row">
              <BarChart3 size={16} />
              <span>
                {evaluation.notice ||
                  "Benchmark results compare synthetic annotations, not legal correctness."}
              </span>
            </div>
            {evaluation.limitations.length > 0 && (
              <ul className="plain-list evaluation-limitations">
                {evaluation.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </Card>

      <div className="dashboard-grid dashboard-grid-wide">
        <Card
          title="Recent contracts"
          subtitle="Latest uploaded agreements"
          action={<Link className="text-link" to="/upload">Manage contracts →</Link>}
        >
          {recentDocuments.length === 0 ? (
            <EmptyState
              icon={<FileText size={26} />}
              title="No contracts uploaded"
              description="Upload a PDF or DOCX to begin the review pipeline."
              action={<Link className="btn btn-primary" to="/upload">Upload contract</Link>}
            />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Contract</th>
                    <th>Status</th>
                    <th>Pages</th>
                    <th>Size</th>
                    <th>Uploaded</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {recentDocuments.map((document) => (
                    <tr key={document.id}>
                      <td>
                        <div className="table-primary">{document.original_filename}</div>
                        <div className="table-secondary">{document.total_characters.toLocaleString()} characters</div>
                      </td>
                      <td>
                        <ToneBadge tone={document.status === "completed" ? "success" : document.status === "failed" ? "danger" : "warning"}>
                          {document.status.replace(/_/g, " ")}
                        </ToneBadge>
                      </td>
                      <td>{document.total_pages || "—"}</td>
                      <td>{formatBytes(document.file_size_bytes)}</td>
                      <td>{formatRelative(document.created_at)}</td>
                      <td>
                        <Link className="text-link" to={`/contracts/${document.id}/review`}>
                          Review <ArrowRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          title="Recent workflow runs"
          subtitle="Latest orchestration and review activity"
          action={<Link className="text-link" to="/history">All runs →</Link>}
        >
          {recentRuns.length === 0 ? (
            <EmptyState
              icon={<FileSearch size={26} />}
              title="No recent runs"
              description="Workflow activity will appear here."
            />
          ) : (
            <div className="run-list">
              {recentRuns.map((run) => (
                <Link
                  className="run-list-item"
                  key={run.workflow_id}
                  to={`/contracts/${run.document_id}/review?workflow=${run.workflow_id}`}
                >
                  <div>
                    <div className="table-primary">
                      {run.review_report?.document_id ? titleCase(run.current_node || "workflow") : "Contract review"}
                    </div>
                    <div className="table-secondary">
                      Step {run.step_count} · {formatRelative(run.created_at)}
                    </div>
                  </div>
                  <WorkflowStatusBadge status={run.status} />
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
