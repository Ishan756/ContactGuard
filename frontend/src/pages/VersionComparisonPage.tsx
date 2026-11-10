import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  GitCompare,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { ToneBadge } from "../components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  PageHeader,
} from "../components/ui/States";
import { apiClient } from "../services/apiClient";
import { getReviewerAuth } from "../services/session";
import type {
  ClauseChangeResponse,
  ClauseChangeType,
  ContractComparisonResponse,
  DocumentMetadataResponse,
  FindingChangeResponse,
  FindingChangeType,
} from "../types/api";
import type { Tone } from "../utils/format";
import { formatDate, titleCase } from "../utils/format";

const clauseTone: Record<ClauseChangeType, Tone> = {
  added: "success",
  removed: "danger",
  modified: "warning",
  unchanged: "neutral",
  reclassified: "violet",
};

const findingTone: Record<FindingChangeType, Tone> = {
  new: "danger",
  resolved: "success",
  persisted: "warning",
  severity_changed: "info",
};

const ClauseChangeCard: React.FC<{ change: ClauseChangeResponse }> = ({ change }) => (
  <div className="change-item">
    <div className="change-item-head">
      <div>
        <strong>{titleCase(change.category)}</strong>
        <span className="table-secondary">
          {change.change_type === "reclassified"
            ? `${titleCase(change.base_category)} → ${titleCase(change.target_category)}`
            : `${Math.round(change.similarity * 100)}% similarity`}
        </span>
      </div>
      <ToneBadge tone={clauseTone[change.change_type]}>{change.change_type}</ToneBadge>
    </div>
    <p className="change-summary">{change.change_summary}</p>
    {change.base_source_text && change.change_type !== "added" && (
      <div className="change-quote change-quote-base">
        <span>Before</span>
        <p>{change.base_source_text}</p>
      </div>
    )}
    {change.target_source_text && change.change_type !== "removed" && (
      <div className="change-quote change-quote-target">
        <span>After</span>
        <p>{change.target_source_text}</p>
      </div>
    )}
  </div>
);

const FindingChangeCard: React.FC<{ change: FindingChangeResponse }> = ({ change }) => (
  <div className="change-item">
    <div className="change-item-head">
      <div>
        <strong>{titleCase(change.risk_category)}</strong>
        <span className="table-secondary">
          {change.finding_type.replace(/_/g, " ")}
          {change.rule_id ? ` · ${change.rule_id}` : ""}
        </span>
      </div>
      <ToneBadge tone={findingTone[change.change_type]}>
        {change.change_type.replace(/_/g, " ")}
      </ToneBadge>
    </div>
    <p className="change-summary">{change.explanation}</p>
    {(change.base_severity || change.target_severity) && (
      <div className="change-severity">
        <span>Severity</span>
        <span>{titleCase(change.base_severity)}</span>
        <ArrowRight size={13} />
        <span>{titleCase(change.target_severity)}</span>
      </div>
    )}
  </div>
);

export const VersionComparisonPage: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentMetadataResponse[]>([]);
  const [comparisons, setComparisons] = useState<ContractComparisonResponse[]>([]);
  const [baseDocumentId, setBaseDocumentId] = useState("");
  const [targetDocumentId, setTargetDocumentId] = useState("");
  const [reanalyze, setReanalyze] = useState(false);
  const [selected, setSelected] = useState<ContractComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const auth = getReviewerAuth();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [documentResponse, comparisonResponse] = await Promise.all([
        apiClient.listDocuments(100, 0),
        apiClient.listComparisons({ limit: 20 }),
      ]);
      setDocuments(documentResponse.documents);
      setComparisons(comparisonResponse.comparisons);
      setSelected((current) => current ?? comparisonResponse.comparisons[0] ?? null);
      if (!baseDocumentId && documentResponse.documents[0]) {
        setBaseDocumentId(documentResponse.documents[0].id);
      }
      if (!targetDocumentId && documentResponse.documents[1]) {
        setTargetDocumentId(documentResponse.documents[1].id);
      }
    } catch (loadError: unknown) {
      setError(
        loadError instanceof Error ? loadError.message : "Unable to load comparisons."
      );
    } finally {
      setLoading(false);
    }
  }, [baseDocumentId, targetDocumentId]);

  useEffect(() => {
    void load();
    // Initial load only; selections are preserved across refreshes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const documentNames = useMemo(
    () => new Map(documents.map((document) => [document.id, document.original_filename])),
    [documents]
  );

  const changedClauses = useMemo(
    () => selected?.clause_changes.filter((item) => item.change_type !== "unchanged") ?? [],
    [selected]
  );

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!baseDocumentId || !targetDocumentId) {
      setFormError("Select both an earlier and a newer contract version.");
      return;
    }
    if (baseDocumentId === targetDocumentId) {
      setFormError("Choose two different contract versions.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await apiClient.createComparison({
        base_document_id: baseDocumentId,
        target_document_id: targetDocumentId,
        reanalyze_target: reanalyze,
      });
      setComparisons((current) => [
        created,
        ...current.filter((item) => item.comparison_id !== created.comparison_id),
      ]);
      setSelected(created);
    } catch (submitError: unknown) {
      setFormError(
        submitError instanceof Error ? submitError.message : "Unable to compare versions."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const documentName = (documentId: string) =>
    documentNames.get(documentId) || `Contract ${documentId.slice(0, 10)}`;

  return (
    <div id="version-comparison-page">
      <PageHeader
        eyebrow="Version control"
        title="Contract version comparison"
        description="Match extracted clauses across two document versions and identify textual, classification, and finding-level changes. Comparison is evidence review support, not a legal opinion."
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

      <Notice tone="info" title="Comparison scope">
        Clause matching is deterministic and finding changes compare the latest analysis runs.
        Re-analysis replays risk analysis for affected clauses and preserves prior audit history.
      </Notice>

      {!auth && (
        <Notice tone="warning" title="Reviewer credentials required">
          Add a reviewer ID and workflow API key in Settings to create a comparison.
        </Notice>
      )}

      <Card title="Compare versions" subtitle="Choose the earlier and newer contract versions">
        <form onSubmit={handleSubmit} className="stack-form">
          <div className="inline-form-row">
            <label className="field">
              <span>Earlier version</span>
              <select
                id="comparison-base-document"
                value={baseDocumentId}
                onChange={(event) => setBaseDocumentId(event.target.value)}
              >
                <option value="">Select a contract</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.original_filename}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Newer version</span>
              <select
                id="comparison-target-document"
                value={targetDocumentId}
                onChange={(event) => setTargetDocumentId(event.target.value)}
              >
                <option value="">Select a contract</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.original_filename}
                  </option>
                ))}
              </select>
            </label>
            <label className="field field-inline field-align-end">
              <input
                type="checkbox"
                checked={reanalyze}
                onChange={(event) => setReanalyze(event.target.checked)}
              />
              <span>Re-analyze changed clauses</span>
            </label>
            <div className="field field-align-end">
              <Button
                type="submit"
                variant="primary"
                disabled={submitting || documents.length < 2}
                icon={<GitCompare size={15} />}
              >
                {submitting ? "Comparing…" : "Compare versions"}
              </Button>
            </div>
          </div>
          {formError && (
            <Notice tone="danger" title="Comparison could not start">
              {formError}
            </Notice>
          )}
          {documents.length < 2 && (
            <span className="table-secondary">
              Upload at least two contract versions to compare them.
            </span>
          )}
        </form>
      </Card>

      {loading ? (
        <LoadingState label="Loading comparisons…" />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : (
        <>
          <Card
            title="Recent comparisons"
            subtitle={`${comparisons.length} stored comparison${comparisons.length === 1 ? "" : "s"}`}
          >
            {comparisons.length === 0 ? (
              <EmptyState
                icon={<GitCompare size={26} />}
                title="No comparisons yet"
                description="Select two contract versions above to create the first comparison."
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Created</th>
                      <th>Versions</th>
                      <th>Clause changes</th>
                      <th>Finding changes</th>
                      <th>Status</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {comparisons.map((comparison) => (
                      <tr key={comparison.comparison_id}>
                        <td>
                          <div className="table-primary">
                            {formatDate(comparison.created_at)}
                          </div>
                          <div className="table-secondary mono">
                            {comparison.comparison_id.slice(0, 12)}
                          </div>
                        </td>
                        <td>
                          <div className="table-primary">
                            {documentName(comparison.base_document_id)}
                          </div>
                          <div className="table-secondary">
                            → {documentName(comparison.target_document_id)}
                          </div>
                        </td>
                        <td>
                          <div className="table-secondary">
                            +{comparison.clauses_added} added · −
                            {comparison.clauses_removed} removed
                          </div>
                          <div className="table-secondary">
                            {comparison.clauses_modified} modified ·{" "}
                            {comparison.clauses_reclassified} reclassified
                          </div>
                        </td>
                        <td>
                          <div className="table-secondary">
                            {comparison.findings_new} new · {comparison.findings_resolved}{" "}
                            resolved
                          </div>
                          <div className="table-secondary">
                            {comparison.findings_persisted} persisted ·{" "}
                            {comparison.findings_severity_changed} severity changed
                          </div>
                        </td>
                        <td>
                          <ToneBadge
                            tone={
                              comparison.status === "completed"
                                ? "success"
                                : comparison.status === "failed"
                                  ? "danger"
                                  : "warning"
                            }
                          >
                            {comparison.status}
                          </ToneBadge>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="text-link text-button"
                            onClick={() => setSelected(comparison)}
                          >
                            Inspect <ArrowRight size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {selected && (
            <>
              <div className="stats-grid stats-grid-compact">
                <Card>
                  <div className="stat-card">
                    <div>
                      <span className="stat-label">Clauses changed</span>
                      <strong className="stat-value">
                        {selected.clauses_added +
                          selected.clauses_removed +
                          selected.clauses_modified +
                          selected.clauses_reclassified}
                      </strong>
                      <span className="stat-meta">
                        {selected.clauses_unchanged} unchanged
                      </span>
                    </div>
                    <span className="stat-icon stat-icon-cyan">
                      <GitCompare size={20} />
                    </span>
                  </div>
                </Card>
                <Card>
                  <div className="stat-card">
                    <div>
                      <span className="stat-label">New findings</span>
                      <strong className="stat-value">{selected.findings_new}</strong>
                      <span className="stat-meta">
                        {selected.findings_resolved} resolved ·{" "}
                        {selected.findings_persisted} persisted
                      </span>
                    </div>
                    <span className="stat-icon stat-icon-rose">
                      <ShieldAlert size={20} />
                    </span>
                  </div>
                </Card>
                <Card>
                  <div className="stat-card">
                    <div>
                      <span className="stat-label">Re-analysis</span>
                      <strong className="stat-value">
                        {selected.reanalysis_performed ? "Run" : "Not run"}
                      </strong>
                      <span className="stat-meta">
                        {selected.reanalysis_requested
                          ? "Requested by reviewer"
                          : "Existing analysis reused"}
                      </span>
                    </div>
                    <span className="stat-icon stat-icon-emerald">
                      {selected.reanalysis_performed ? (
                        <CheckCircle2 size={20} />
                      ) : (
                        <XCircle size={20} />
                      )}
                    </span>
                  </div>
                </Card>
              </div>

              {selected.warnings.length > 0 && (
                <Notice tone="warning" title="Comparison warnings">
                  <ul className="plain-list">
                    {selected.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </Notice>
              )}

              <div className="dashboard-grid dashboard-grid-wide">
                <Card
                  title="Clause changes"
                  subtitle="Text and category differences between versions"
                >
                  {changedClauses.length === 0 ? (
                    <EmptyState
                      icon={<CheckCircle2 size={26} />}
                      title="No changed clauses"
                      description="All matched clauses are textually and categorically unchanged."
                    />
                  ) : (
                    <div className="change-list">
                      {changedClauses.map((change) => (
                        <ClauseChangeCard change={change} key={change.change_id} />
                      ))}
                    </div>
                  )}
                </Card>
                <Card
                  title="Finding changes"
                  subtitle="Latest analysis findings compared across versions"
                >
                  {selected.finding_changes.length === 0 ? (
                    <EmptyState
                      icon={<CheckCircle2 size={26} />}
                      title="No finding changes"
                      description="No finding-level differences were recorded for this comparison."
                    />
                  ) : (
                    <div className="change-list">
                      {selected.finding_changes.map((change) => (
                        <FindingChangeCard change={change} key={change.change_id} />
                      ))}
                    </div>
                  )}
                </Card>
              </div>

              <Notice tone="info" title="Interpretation">
                {selected.notice}
              </Notice>
            </>
          )}
        </>
      )}
    </div>
  );
};
