import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  FileText,
  HelpCircle,
  MapPin,
  Sparkles,
  Tag,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import {
  ReviewBadge,
  SeverityBadge,
  ToneBadge,
  ValidationBadge,
} from "../components/ui/StatusBadge";
import { ErrorState, LoadingState, Notice, PageHeader } from "../components/ui/States";
import { apiClient } from "../services/apiClient";
import type { RiskFindingResponse } from "../types/api";
import { formatDate, sourcePage, titleCase } from "../utils/format";

export const FindingDetailPage: React.FC = () => {
  const { documentId = "", findingId = "" } = useParams();
  const [finding, setFinding] = useState<RiskFindingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setFinding(await apiClient.getFinding(documentId, findingId));
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Unable to load this finding.");
    } finally {
      setLoading(false);
    }
  }, [documentId, findingId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingState label="Loading finding…" />;
  if (error || !finding) {
    return (
      <ErrorState
        title="Finding unavailable"
        message={error || "This finding could not be found."}
        onRetry={() => void load()}
      />
    );
  }

  const page = sourcePage(finding.contract_source_reference, finding.contract_page_number);
  const reviewPath = `/contracts/${documentId}/review?finding=${finding.finding_id}${
    page ? `&page=${page}` : ""
  }`;
  const policyPath = finding.policy_id
    ? `/policies?policy=${finding.policy_id}`
    : "/policies";

  return (
    <div id="finding-detail-page">
      <Link className="text-link back-link" to={`/findings?document=${documentId}`}>
        <ArrowLeft size={14} /> Back to findings
      </Link>
      <PageHeader
        eyebrow={`${finding.finding_type.replace(/_/g, " ")} · ${titleCase(finding.risk_category)}`}
        title="Finding evidence and review guidance"
        description={`Created ${formatDate(finding.created_at)} · analysis model ${finding.analysis_model}`}
        actions={
          <>
            <Link className="btn btn-secondary" to={policyPath}>
              <BookOpen size={15} /> Policy library
            </Link>
            <Link className="btn btn-primary" to={reviewPath}>
              <FileText size={15} /> Open cited contract text
            </Link>
          </>
        }
      />

      <div className="finding-detail-badges">
        <SeverityBadge severity={finding.severity} />
        <ValidationBadge status={finding.validation_status} />
        <ReviewBadge status={finding.review_status} />
        <ToneBadge tone="neutral">{finding.severity_basis.replace(/_/g, " ")}</ToneBadge>
        {finding.rule_id && <ToneBadge tone="info">Rule {finding.rule_id}</ToneBadge>}
      </div>

      {finding.validation_status !== "verified" && (
        <Notice tone="warning" title="This finding is not independently verified">
          Validation outcome: <strong>{finding.validation_status.replace(/_/g, " ")}</strong>. Do
          not treat this finding as verified evidence until the source citations have been reviewed.
        </Notice>
      )}

      <div className="finding-detail-grid">
        <Card
          title="Contract quotation"
          subtitle="Verbatim text from the uploaded agreement"
          action={
            page ? (
              <Link className="text-link" to={reviewPath}>
                <MapPin size={14} /> Page {page}
              </Link>
            ) : undefined
          }
        >
          {finding.contract_quote ? (
            <blockquote className="quote-block quote-contract">{finding.contract_quote}</blockquote>
          ) : (
            <p className="muted-text">No contract quotation was captured for this finding.</p>
          )}
          <div className="citation-meta">
            <span>Source: {finding.contract_source_reference || "not provided"}</span>
            {finding.contract_page_number && <span>Page {finding.contract_page_number}</span>}
          </div>
        </Card>

        <Card
          title="Policy quotation"
          subtitle="Retrieved company policy evidence"
          action={
            finding.policy_id ? (
              <Link className="text-link" to={policyPath}>
                Open policy <ArrowUpRight size={14} />
              </Link>
            ) : undefined
          }
        >
          {finding.policy_quote ? (
            <blockquote className="quote-block quote-policy">{finding.policy_quote}</blockquote>
          ) : (
            <p className="muted-text">No policy quotation is attached to this finding.</p>
          )}
          <div className="citation-meta">
            <span>Source: {finding.policy_source_reference || "not provided"}</span>
            {finding.policy_page_number && <span>Page {finding.policy_page_number}</span>}
            {finding.policy_version && <span>Policy version {finding.policy_version}</span>}
          </div>
        </Card>
      </div>

      <div className="finding-detail-grid">
        <Card title="Model-generated explanation" subtitle="Interpretation, not original contract text">
          <div className="model-explanation">
            <div className="source-label source-label-model">
              <Sparkles size={13} /> Generated by {finding.analysis_model}
            </div>
            <p>{finding.explanation}</p>
            {finding.confidence !== null && finding.confidence !== undefined && (
              <div className="citation-meta">
                Model confidence: {(finding.confidence * 100).toFixed(0)}% · never used as a
                substitute for evidence validation
              </div>
            )}
          </div>
        </Card>

        <Card title="Suggested reviewer question" subtitle="Follow-up prompt for human review">
          <div className="reviewer-question">
            <HelpCircle size={20} />
            <p>{finding.suggested_question}</p>
          </div>
        </Card>
      </div>

      <Card title="Validation and provenance" subtitle="Independent evidence checks and source metadata">
        <div className="detail-grid">
          <div><span>Validation status</span><ValidationBadge status={finding.validation_status} /></div>
          <div><span>Validation attempts</span><strong>{finding.validation_attempts}</strong></div>
          <div><span>Last validated</span><strong>{formatDate(finding.last_validated_at)}</strong></div>
          <div><span>Review status</span><ReviewBadge status={finding.review_status} /></div>
          <div><span>Finding type</span><strong>{titleCase(finding.finding_type)}</strong></div>
          <div><span>Severity basis</span><strong>{titleCase(finding.severity_basis)}</strong></div>
          <div><span>Clause</span><strong>{finding.clause_id ? finding.clause_id.slice(0, 12) : "—"}</strong></div>
          <div><span>Risk category</span><strong>{titleCase(finding.risk_category)}</strong></div>
        </div>

        {finding.validation_error_categories.length > 0 && (
          <>
            <div className="card-divider" />
            <div className="detail-subhead">
              <Tag size={14} /> Validation issues
            </div>
            <div className="chip-row">
              {finding.validation_error_categories.map((category) => (
                <ToneBadge tone="warning" key={category}>
                  {category.replace(/_/g, " ")}
                </ToneBadge>
              ))}
            </div>
          </>
        )}

        {finding.policy_versions.length > 0 && (
          <>
            <div className="card-divider" />
            <div className="detail-subhead">Policy versions considered</div>
            <div className="chip-row">
              {finding.policy_versions.map((version) => (
                <ToneBadge tone="neutral" key={version}>v{version}</ToneBadge>
              ))}
            </div>
          </>
        )}

        <div className="card-divider" />
        <div className="detail-actions">
          <Link className="btn btn-primary" to={reviewPath}>
            Open cited source location
          </Link>
          <Button variant="secondary" onClick={() => void load()}>
            Refresh finding
          </Button>
        </div>
      </Card>
    </div>
  );
};
