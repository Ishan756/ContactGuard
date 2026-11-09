import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileClock,
  FilterX,
  RefreshCw,
  Users,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { ReviewBadge, ToneBadge, WorkflowStatusBadge } from "../components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
} from "../components/ui/States";
import { apiClient } from "../services/apiClient";
import type {
  DocumentMetadataResponse,
  ReviewDecisionType,
  WorkflowRunResponse,
} from "../types/api";
import { formatDate, titleCase } from "../utils/format";

const PAGE_SIZE = 10;
type DateRange = "all" | "7" | "30" | "90";

export const ReviewHistoryPage: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentMetadataResponse[]>([]);
  const [runs, setRuns] = useState<WorkflowRunResponse[]>([]);
  const [documentId, setDocumentId] = useState("all");
  const [decision, setDecision] = useState("all");
  const [status, setStatus] = useState("all");
  const [dateRange, setDateRange] = useState<DateRange>("all");
  const [reviewer, setReviewer] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [documentResponse, workflowResponse] = await Promise.all([
        apiClient.listDocuments(100, 0),
        apiClient.listWorkflows({
          documentId: documentId === "all" ? undefined : documentId,
          limit: 100,
        }),
      ]);
      setDocuments(documentResponse.documents);
      setRuns(workflowResponse.runs);
      setPage(1);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Unable to load review history.");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const documentNames = useMemo(
    () => new Map(documents.map((document) => [document.id, document.original_filename])),
    [documents]
  );

  const filtered = useMemo(() => {
    const needle = reviewer.trim().toLowerCase();
    const cutoff =
      dateRange === "all"
        ? null
        : Date.now() - Number(dateRange) * 24 * 60 * 60 * 1000;
    return runs
      .filter((run) => {
        if (status !== "all" && run.status !== status) return false;
        if (decision !== "all" && !run.decisions.some((item) => item.decision === decision)) {
          return false;
        }
        if (needle) {
          const matchesReviewer =
            run.owner_reviewer_id.toLowerCase().includes(needle) ||
            run.decisions.some((item) => item.reviewer_id.toLowerCase().includes(needle));
          if (!matchesReviewer) return false;
        }
        if (cutoff && new Date(run.created_at).getTime() < cutoff) return false;
        return true;
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [runs, status, decision, reviewer, dateRange]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paged = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const totalDecisions = filtered.reduce((sum, run) => sum + run.decisions.length, 0);
  const completed = filtered.filter((run) => run.status === "completed").length;

  const resetFilters = () => {
    setDecision("all");
    setStatus("all");
    setDateRange("all");
    setReviewer("");
    setPage(1);
  };

  return (
    <div id="review-history-page">
      <PageHeader
        eyebrow="Human oversight"
        title="Review history"
        description="Audit workflow decisions, reviewer ownership, retries, revisions, and completion outcomes. History is scoped to your reviewer identity."
        actions={
          <Button
            variant="secondary"
            onClick={() => void load()}
            disabled={loading}
            icon={<RefreshCw size={14} className={loading ? "spin" : ""} />}
          >
            Refresh
          </Button>
        }
      />

      <div className="stats-grid stats-grid-compact">
        <Card><div className="stat-card"><span className="stat-label">Runs shown</span><strong className="stat-value">{filtered.length}</strong><span className="stat-meta">Matching current filters</span></div></Card>
        <Card><div className="stat-card"><span className="stat-label">Completed</span><strong className="stat-value">{completed}</strong><span className="stat-meta">Human review finished</span></div></Card>
        <Card><div className="stat-card"><span className="stat-label">Decisions</span><strong className="stat-value">{totalDecisions}</strong><span className="stat-meta">Approve, dismiss, revise</span></div></Card>
      </div>

      <Card style={{ marginBottom: "1rem" }}>
        <div className="filter-grid">
          <label className="field">
            <span>Contract</span>
            <select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
              <option value="all">All contracts</option>
              {documents.map((document) => (
                <option value={document.id} key={document.id}>{document.original_filename}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Run status</span>
            <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
              <option value="all">All statuses</option>
              {["pending", "running", "awaiting_review", "revising", "completed", "failed", "cancelled"].map((item) => (
                <option value={item} key={item}>{titleCase(item)}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Decision</span>
            <select value={decision} onChange={(event) => { setDecision(event.target.value); setPage(1); }}>
              <option value="all">Any decision</option>
              {(["approve", "dismiss", "request_revision"] as ReviewDecisionType[]).map((item) => (
                <option value={item} key={item}>{titleCase(item)}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Time range</span>
            <select value={dateRange} onChange={(event) => { setDateRange(event.target.value as DateRange); setPage(1); }}>
              <option value="all">All time</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </select>
          </label>
          <label className="field">
            <span>Reviewer</span>
            <input
              type="search"
              value={reviewer}
              onChange={(event) => { setReviewer(event.target.value); setPage(1); }}
              placeholder="Filter by reviewer ID"
            />
          </label>
          <div className="field field-align-end">
            <Button variant="secondary" onClick={resetFilters} icon={<FilterX size={14} />}>Reset</Button>
          </div>
        </div>
      </Card>

      {loading ? (
        <LoadingState label="Loading review history…" />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon={<FileClock size={28} />}
            title="No review history matches"
            description="Run a contract review or adjust the filters to see prior decisions."
            action={<Button variant="secondary" onClick={resetFilters}>Clear filters</Button>}
          />
        </Card>
      ) : (
        <>
          <Card>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Contract / workflow</th>
                    <th>Run</th>
                    <th>Evidence</th>
                    <th>Reviewer activity</th>
                    <th>Dates</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {paged.map((run) => {
                    const decisions = run.decisions;
                    const summary = run.review_report?.summary;
                    return (
                      <tr key={run.workflow_id}>
                        <td>
                          <div className="table-primary">
                            {documentNames.get(run.document_id) || `Contract ${run.document_id.slice(0, 10)}`}
                          </div>
                          <div className="table-secondary mono">{run.workflow_id.slice(0, 12)}</div>
                        </td>
                        <td>
                          <WorkflowStatusBadge status={run.status} />
                          <div className="table-secondary">
                            {run.current_node || "—"} · step {run.step_count}/{run.max_steps}
                          </div>
                          {run.retry_count > 0 && (
                            <div className="table-secondary">{run.retry_count} automatic retries</div>
                          )}
                          {run.revision_count > 0 && (
                            <div className="table-secondary">{run.revision_count} human revisions</div>
                          )}
                        </td>
                        <td>
                          {summary ? (
                            <div className="table-stack">
                              <span><strong>{summary.findings}</strong> findings</span>
                              <span className="tone-success"><CheckCircle2 size={12} /> {summary.verified} verified</span>
                              {summary.unverified > 0 && <span className="tone-warning">{summary.unverified} unverified</span>}
                            </div>
                          ) : (
                            <span className="muted-text">Report pending</span>
                          )}
                        </td>
                        <td>
                          <div className="table-primary reviewer-cell">
                            <Users size={13} /> {run.owner_reviewer_id}
                          </div>
                          {decisions.length === 0 ? (
                            <ReviewBadge status="needs_review" />
                          ) : (
                            <div className="table-stack">
                              {decisions.slice(-2).map((item) => (
                                <div key={item.decision_id} className="decision-line">
                                  <ToneBadge
                                    tone={
                                      item.decision === "approve"
                                        ? "success"
                                        : item.decision === "dismiss"
                                          ? "neutral"
                                          : "warning"
                                    }
                                  >
                                    {item.decision.replace(/_/g, " ")}
                                  </ToneBadge>
                                  <span className="table-secondary">{item.reviewer_id}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                        <td>
                          <div className="table-secondary">
                            <Clock3 size={12} /> Started {formatDate(run.started_at || run.created_at)}
                          </div>
                          <div className="table-secondary">
                            Completed {formatDate(run.completed_at)}
                          </div>
                        </td>
                        <td>
                          <Link className="text-link" to={`/contracts/${run.document_id}/review?workflow=${run.workflow_id}`}>
                            Open <ArrowRight size={13} />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
          <Pagination
            page={currentPage}
            pageSize={PAGE_SIZE}
            total={filtered.length}
            label="workflow runs"
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
};
