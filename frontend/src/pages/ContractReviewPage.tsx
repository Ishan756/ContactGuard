import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  FileSearch,
  FileText,
  MessageSquareWarning,
  Play,
  RefreshCw,
  RotateCcw,
  Settings,
  XCircle,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { ToneBadge, WorkflowStatusBadge } from "../components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  ProgressBar,
} from "../components/ui/States";
import { DocumentViewer } from "../components/domain/DocumentViewer";
import { FindingCard } from "../components/domain/FindingCard";
import { apiClient, ApiClientError } from "../services/apiClient";
import { getReviewerAuth } from "../services/session";
import type {
  ClauseResponse,
  DocumentChunkResponse,
  DocumentMetadataResponse,
  ReviewDecisionType,
  RetryTarget,
  RiskFindingResponse,
  WorkflowResultsResponse,
  WorkflowRunResponse,
} from "../types/api";
import { formatDate, titleCase } from "../utils/format";

const ACTIONS: Array<{
  value: ReviewDecisionType;
  label: string;
  icon: React.ReactNode;
  description: string;
}> = [
  {
    value: "approve",
    label: "Approve review",
    icon: <CheckCircle2 size={15} />,
    description: "Acknowledge the review without executing any legal action.",
  },
  {
    value: "dismiss",
    label: "Dismiss finding(s)",
    icon: <XCircle size={15} />,
    description: "Mark the selected findings as not requiring action.",
  },
  {
    value: "request_revision",
    label: "Request revision",
    icon: <RotateCcw size={15} />,
    description: "Send the workflow back for another analysis or retrieval pass.",
  },
];

export const ContractReviewPage: React.FC = () => {
  const { documentId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const requestedWorkflowId = searchParams.get("workflow");
  const activeFindingId = searchParams.get("finding");
  const requestedPage = Number(searchParams.get("page") || "1");

  const [document, setDocument] = useState<DocumentMetadataResponse | null>(null);
  const [chunks, setChunks] = useState<DocumentChunkResponse[]>([]);
  const [clauses, setClauses] = useState<ClauseResponse[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowRunResponse[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowRunResponse | null>(null);
  const [results, setResults] = useState<WorkflowResultsResponse | null>(null);
  const [findings, setFindings] = useState<RiskFindingResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [activePage, setActivePage] = useState(Number.isFinite(requestedPage) ? requestedPage : 1);
  const [selectedFindingIds, setSelectedFindingIds] = useState<Set<string>>(new Set());
  const [action, setAction] = useState<ReviewDecisionType>("approve");
  const [notes, setNotes] = useState("");
  const [instructions, setInstructions] = useState("");
  const [revisionTarget, setRevisionTarget] = useState<RetryTarget>("analysis");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const loadSequence = useRef(0);

  const auth = getReviewerAuth();

  const loadFindingsFallback = useCallback(async () => {
    try {
      const response = await apiClient.listFindings(documentId, { limit: 500 });
      setFindings(response.findings);
    } catch {
      setFindings([]);
    }
  }, [documentId]);

  const loadWorkflow = useCallback(
    async (workflowId: string) => {
      const sequence = ++loadSequence.current;
      try {
        const [run, workflowResults] = await Promise.all([
          apiClient.getWorkflow(workflowId),
          apiClient.getWorkflowResults(workflowId),
        ]);
        if (sequence !== loadSequence.current) return;
        setWorkflow(run);
        setResults(workflowResults);
        setFindings(workflowResults.findings);
        setWorkflowError(null);
      } catch (error: unknown) {
        if (sequence !== loadSequence.current) return;
        setWorkflowError(error instanceof Error ? error.message : "Unable to load workflow results.");
        await loadFindingsFallback();
      }
    },
    [loadFindingsFallback]
  );

  const loadBase = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [documentResult, chunksResult, clausesResult, workflowResult] = await Promise.allSettled([
      apiClient.getDocument(documentId),
      apiClient.getDocumentChunks(documentId, 1, 100),
      apiClient.listClauses(documentId, 250),
      apiClient.listWorkflows({ documentId, limit: 30 }),
    ]);

    if (documentResult.status === "fulfilled") {
      setDocument(documentResult.value);
    } else {
      setError(
        documentResult.reason instanceof Error
          ? documentResult.reason.message
          : "Unable to load this contract."
      );
    }
    setChunks(chunksResult.status === "fulfilled" ? chunksResult.value.chunks : []);
    setClauses(clausesResult.status === "fulfilled" ? clausesResult.value.clauses : []);

    if (workflowResult.status === "fulfilled") {
      setWorkflows(workflowResult.value.runs);
      const requested = requestedWorkflowId
        ? workflowResult.value.runs.find((run) => run.workflow_id === requestedWorkflowId)
        : undefined;
      const chosen = requested ?? workflowResult.value.runs[0];
      if (chosen) {
        await loadWorkflow(chosen.workflow_id);
      } else {
        setWorkflow(null);
        setResults(null);
        await loadFindingsFallback();
      }
    } else {
      setWorkflows([]);
      setWorkflow(null);
      setResults(null);
      setWorkflowError(
        workflowResult.reason instanceof ApiClientError
          ? workflowResult.reason.message
          : "Unable to load workflow data."
      );
      await loadFindingsFallback();
    }
    setLoading(false);
  }, [documentId, loadFindingsFallback, loadWorkflow, requestedWorkflowId]);

  useEffect(() => {
    void loadBase();
  }, [loadBase]);

  useEffect(() => {
    setSelectedFindingIds(new Set(findings.map((finding) => finding.finding_id)));
  }, [findings]);

  const isActive = workflow?.status === "running" || workflow?.status === "pending" || workflow?.status === "revising";

  useEffect(() => {
    if (!workflow || !isActive || !auth) return;
    const interval = window.setInterval(() => {
      void loadWorkflow(workflow.workflow_id);
    }, 3000);
    return () => window.clearInterval(interval);
  }, [workflow, isActive, auth, loadWorkflow]);

  const activeFinding = useMemo(
    () => findings.find((finding) => finding.finding_id === activeFindingId) || null,
    [findings, activeFindingId]
  );

  useEffect(() => {
    if (activeFinding) {
      setActivePage(activeFinding.contract_page_number || activePage);
    }
  }, [activeFinding]); // eslint-disable-line react-hooks/exhaustive-deps

  const summary = results?.report?.summary;
  const validation = results?.validation_summary;
  const canReview = workflow?.status === "awaiting_review" && Boolean(auth);
  const allSelected = findings.length > 0 && selectedFindingIds.size === findings.length;

  const toggleFinding = (findingId: string, selected: boolean) => {
    setSelectedFindingIds((current) => {
      const next = new Set(current);
      if (selected) next.add(findingId);
      else next.delete(findingId);
      return next;
    });
  };

  const startReview = async () => {
    if (!auth) return;
    setStarting(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const run = await apiClient.startWorkflow(
        { document_id: documentId },
        `ui-start-${documentId}-${Date.now()}`
      );
      setWorkflow(run);
      setWorkflows((current) => [run, ...current]);
      await loadWorkflow(run.workflow_id);
      setActionMessage("Review workflow started.");
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : "Unable to start the workflow.");
    } finally {
      setStarting(false);
    }
  };

  const submitDecision = async () => {
    if (!workflow || !auth) return;
    if (action === "request_revision" && !instructions.trim() && !notes.trim()) {
      setActionError("Add revision instructions before requesting another pass.");
      return;
    }
    setActionBusy(true);
    setActionError(null);
    setActionMessage(null);
    try {
      await apiClient.resumeWorkflow(
        workflow.workflow_id,
        {
          decision: action,
          finding_ids: selectedFindingIds.size > 0 ? Array.from(selectedFindingIds) : undefined,
          notes: notes.trim() || undefined,
          revision_instructions:
            action === "request_revision" ? instructions.trim() || notes.trim() : undefined,
          revision_target: action === "request_revision" ? revisionTarget : undefined,
        },
        `ui-resume-${workflow.workflow_id}-${Date.now()}`
      );
      setNotes("");
      setInstructions("");
      setActionMessage(`Decision recorded: ${action.replace(/_/g, " ")}.`);
      await loadWorkflow(workflow.workflow_id);
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : "Unable to record the decision.");
    } finally {
      setActionBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Loading review workspace…" />;
  }
  if (error && !document) {
    return (
      <ErrorState
        title="Contract unavailable"
        message={error}
        onRetry={() => void loadBase()}
      />
    );
  }

  return (
    <div id="contract-review-page">
      <div className="review-topbar">
        <div>
          <Link to="/upload" className="text-link back-link">
            <ArrowLeft size={14} /> Back to contracts
          </Link>
          <div className="eyebrow">Contract review workspace</div>
          <h2 className="page-title">{document?.original_filename || "Contract"}</h2>
          <div className="review-subtitle">
            <span>{document?.total_pages || "—"} pages</span>
            <span>{clauses.length} extracted clauses</span>
            <span>{findings.length} findings</span>
            {workflow && <WorkflowStatusBadge status={workflow.status} />}
          </div>
        </div>
        <div className="page-header-actions">
          <Button
            variant="secondary"
            onClick={() => void loadBase()}
            icon={<RefreshCw size={14} />}
          >
            Refresh
          </Button>
          {!workflow && auth && document?.status === "completed" && (
            <Button onClick={startReview} disabled={starting} icon={<Play size={15} />}>
              {starting ? "Starting…" : "Start review"}
            </Button>
          )}
          {activeFindingId && workflow && (
            <Link className="btn btn-secondary" to={`/contracts/${documentId}/review?workflow=${workflow.workflow_id}`}>
              Clear finding focus
            </Link>
          )}
        </div>
      </div>

      {!auth && (
        <Notice tone="warning" title="Reviewer credentials required">
          Set your reviewer ID and API key in <Link to="/settings">Settings</Link> to start or
          action workflows.
        </Notice>
      )}
      {workflowError && (
        <Notice tone={auth ? "danger" : "warning"} title="Workflow status unavailable">
          {workflowError}
        </Notice>
      )}
      {workflow?.error_message && (
        <Notice tone="danger" title={`Workflow failed${workflow.error_code ? ` (${workflow.error_code})` : ""}`}>
          {workflow.error_message}
        </Notice>
      )}
      {actionError && (
        <Notice tone="danger" title="Reviewer action failed">
          {actionError}
        </Notice>
      )}
      {actionMessage && <Notice tone="success">{actionMessage}</Notice>}

      {isActive && (
        <Card style={{ marginBottom: "1rem" }}>
          <ProgressBar
            label={`${titleCase(workflow?.current_node || "workflow")} · step ${
              workflow?.step_count ?? 0
            } of ${workflow?.max_steps ?? 0}`}
            indeterminate
          />
          <p className="muted-text">
            The backend is processing real workflow events. This panel refreshes automatically.
          </p>
        </Card>
      )}

      {summary && (
        <div className="review-summary-strip">
          <div><span>Clauses</span><strong>{summary.clauses_extracted}</strong></div>
          <div><span>Policy evidence</span><strong>{summary.policy_evidence_retrieved}</strong></div>
          <div><span>Findings</span><strong>{summary.findings}</strong></div>
          <div><span>Verified</span><strong>{summary.verified}</strong></div>
          <div><span>Unverified</span><strong>{summary.unverified}</strong></div>
          <div><span>Missing evidence</span><strong>{summary.missing_evidence}</strong></div>
        </div>
      )}

      <div className="review-workspace">
        <div className="review-document-column">
          <DocumentViewer
            document={document}
            chunks={chunks}
            activePage={activePage}
            onPageChange={setActivePage}
            finding={activeFinding}
            error={error}
            onRetry={() => void loadBase()}
          />
        </div>

        <aside className="review-findings-column" aria-label="Findings panel">
          <Card
            title="Findings panel"
            subtitle={
              validation
                ? `${validation.verified_count ?? 0} verified · ${
                    validation.unverified_count ?? 0
                  } unverified · ${validation.missing_evidence_count ?? 0} missing evidence`
                : `${findings.length} findings from the latest analysis`
            }
            action={
              findings.length > 0 ? (
                <label className="finding-select">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(event) =>
                      setSelectedFindingIds(
                        event.target.checked
                          ? new Set(findings.map((finding) => finding.finding_id))
                          : new Set()
                      )
                    }
                  />
                  <span>Select all</span>
                </label>
              ) : undefined
            }
          >
            {findings.length === 0 ? (
              <EmptyState
                icon={<FileSearch size={26} />}
                title={workflow ? "No findings in this run" : "No review workflow yet"}
                description={
                  workflow
                    ? "The automated analysis did not raise any findings for this run."
                    : "Start a review to extract clauses, retrieve policy evidence, and analyze risk."
                }
                action={
                  !workflow && auth && document?.status === "completed" ? (
                    <Button onClick={startReview} disabled={starting} icon={<Play size={15} />}>
                      {starting ? "Starting…" : "Start review"}
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <div className="review-findings-list">
                {findings.map((finding) => (
                  <FindingCard
                    key={finding.finding_id}
                    finding={finding}
                    documentId={documentId}
                    selected={selectedFindingIds.has(finding.finding_id)}
                    onToggle={toggleFinding}
                    compact
                  />
                ))}
              </div>
            )}
          </Card>

          {workflow?.status === "awaiting_review" && (
            <Card
              title="Reviewer decision"
              subtitle="Decisions are appended to an immutable audit trail and never execute legal actions."
            >
              {!canReview ? (
                <Notice tone="warning">
                  Configure reviewer credentials in <Link to="/settings">Settings</Link>.
                </Notice>
              ) : (
                <form
                  className="reviewer-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitDecision();
                  }}
                >
                  <div className="action-choice-grid" role="radiogroup" aria-label="Review decision">
                    {ACTIONS.map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        className={`action-choice ${action === item.value ? "active" : ""}`}
                        aria-pressed={action === item.value}
                        onClick={() => setAction(item.value)}
                      >
                        <span className="action-choice-title">
                          {item.icon} {item.label}
                        </span>
                        <span className="action-choice-description">{item.description}</span>
                      </button>
                    ))}
                  </div>

                  {action === "request_revision" && (
                    <label className="field">
                      <span>Revision instructions</span>
                      <textarea
                        rows={3}
                        value={instructions}
                        onChange={(event) => setInstructions(event.target.value)}
                        placeholder="Explain what the analysis or retrieval pass should correct."
                      />
                    </label>
                  )}

                  {action === "request_revision" && (
                    <label className="field">
                      <span>Revision target</span>
                      <select
                        value={revisionTarget}
                        onChange={(event) => setRevisionTarget(event.target.value as RetryTarget)}
                      >
                        <option value="analysis">Re-run risk analysis</option>
                        <option value="retrieval">Re-run policy retrieval</option>
                      </select>
                    </label>
                  )}

                  <label className="field">
                    <span>Reviewer notes {action === "request_revision" ? "(optional)" : ""}</span>
                    <textarea
                      rows={2}
                      value={notes}
                      onChange={(event) => setNotes(event.target.value)}
                      placeholder="Optional context retained in the audit trail."
                    />
                  </label>

                  <div className="reviewer-form-footer">
                    <span className="muted-text">
                      {selectedFindingIds.size} of {findings.length} findings selected
                    </span>
                    <Button type="submit" disabled={actionBusy} icon={<ClipboardCheck size={15} />}>
                      {actionBusy ? "Recording…" : "Submit decision"}
                    </Button>
                  </div>
                </form>
              )}
            </Card>
          )}

          {workflow && workflow.status !== "awaiting_review" && (
            <Card title="Workflow context" subtitle={`Created ${formatDate(workflow.created_at)}`}>
              <div className="context-list">
                <div><span>Status</span><WorkflowStatusBadge status={workflow.status} /></div>
                <div><span>Current node</span><strong>{workflow.current_node || "—"}</strong></div>
                <div><span>Steps</span><strong>{workflow.step_count} / {workflow.max_steps}</strong></div>
                <div><span>Retries</span><strong>{workflow.retry_count} / {workflow.max_retries}</strong></div>
                <div><span>Human revisions</span><strong>{workflow.revision_count}</strong></div>
                <div><span>Decisions</span><strong>{workflow.decisions.length}</strong></div>
              </div>
              {workflow.decisions.length > 0 && (
                <div className="card-divider" />
              )}
              <Link className="text-link" to={`/history?workflow=${workflow.workflow_id}`}>
                Open full audit trail →
              </Link>
            </Card>
          )}

          {workflows.length > 1 && (
            <Card title="Run history for this contract" subtitle={`${workflows.length} runs`}>
              <div className="run-list">
                {workflows.map((run) => (
                  <Link
                    className={`run-list-item ${run.workflow_id === workflow?.workflow_id ? "active" : ""}`}
                    key={run.workflow_id}
                    to={`/contracts/${documentId}/review?workflow=${run.workflow_id}`}
                  >
                    <div>
                      <div className="table-primary">{formatDate(run.created_at)}</div>
                      <div className="table-secondary">
                        {run.step_count} steps · {run.decisions.length} decisions
                      </div>
                    </div>
                    <WorkflowStatusBadge status={run.status} />
                  </Link>
                ))}
              </div>
            </Card>
          )}
        </aside>
      </div>

      <Card title="Document intelligence" subtitle="Extracted clauses and source validation">
        <div className="clause-grid">
          {clauses.length === 0 ? (
            <EmptyState
              icon={<FileText size={24} />}
              title="No extracted clauses"
              description="Clause extraction runs as part of the review workflow."
            />
          ) : (
            clauses.slice(0, 12).map((clause) => (
              <div className="clause-card" key={clause.clause_id}>
                <div className="clause-card-head">
                  <ToneBadge tone={clause.validation_status === "valid" ? "success" : "warning"}>
                    {titleCase(clause.validation_status)}
                  </ToneBadge>
                  <span>{titleCase(clause.category)}</span>
                  {clause.page_number && <span>p. {clause.page_number}</span>}
                </div>
                <p>{clause.normalized_summary}</p>
                <div className="clause-card-meta">
                  <FileText size={12} /> Model summary · original text remains authoritative
                </div>
              </div>
            ))
          )}
        </div>
        {clauses.length > 12 && (
          <p className="table-secondary">
            Showing 12 of {clauses.length} clauses. Open the Findings view for the complete set.
          </p>
        )}
      </Card>

      {workflow?.status === "completed" && (
        <div className="review-completed-banner">
          <CheckCircle2 size={18} />
          <div>
            <strong>Review completed.</strong> No legal or contractual action was executed.
            {workflow.decisions.length > 0 && " Human decisions are preserved in Review History."}
          </div>
        </div>
      )}
      {workflow?.status === "failed" && (
        <div className="review-failed-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>Review workflow failed.</strong> Fix the underlying issue and start a new run.
          </div>
        </div>
      )}
      {workflow?.status === "awaiting_review" && (
        <div className="review-review-banner">
          <MessageSquareWarning size={18} />
          <div>
            <strong>Human review required.</strong> Verify quoted evidence before approving or
            dismissing findings.
          </div>
        </div>
      )}
      {!workflow && auth && document?.status === "completed" && (
        <div className="review-empty-banner">
          <Settings size={18} />
          <div>
            <strong>No review has been started.</strong> Start a review to run clause extraction,
            retrieval, risk analysis, and independent evidence validation.
          </div>
        </div>
      )}
    </div>
  );
};
