import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, FileText, MapPin, ShieldAlert, Sparkles } from "lucide-react";
import type { RiskFindingResponse } from "../../types/api";
import { reviewTone, severityTone, truncate } from "../../utils/format";
import { ToneBadge } from "../ui/StatusBadge";
import { ValidationBadge } from "../ui/StatusBadge";

interface FindingCardProps {
  finding: RiskFindingResponse;
  documentId: string;
  selected?: boolean;
  onToggle?: (findingId: string, selected: boolean) => void;
  compact?: boolean;
}

export const FindingCard: React.FC<FindingCardProps> = ({
  finding,
  documentId,
  selected = false,
  onToggle,
  compact = false,
}) => {
  const page = finding.contract_page_number;
  const detailPath = `/findings/${documentId}/${finding.finding_id}`;
  const sourcePath = `/contracts/${documentId}/review?finding=${finding.finding_id}${
    page ? `&page=${page}` : ""
  }`;

  return (
    <article
      id={`finding-${finding.finding_id}`}
      className={`finding-card ${selected ? "finding-card-selected" : ""} ${
        compact ? "finding-card-compact" : ""
      }`}
      aria-label={`${finding.severity} finding: ${finding.risk_category}`}
    >
      <div className="finding-card-top">
        <div className="finding-card-badges">
          <ToneBadge tone={severityTone(finding.severity)}>{finding.severity}</ToneBadge>
          <ValidationBadge status={finding.validation_status} />
          <ToneBadge tone={reviewTone(finding.review_status)}>
            {finding.review_status.replace(/_/g, " ")}
          </ToneBadge>
          <ToneBadge tone="neutral">{finding.risk_category.replace(/_/g, " ")}</ToneBadge>
        </div>
        {onToggle && (
          <label className="finding-select">
            <input
              type="checkbox"
              checked={selected}
              onChange={(event) => onToggle(finding.finding_id, event.target.checked)}
              aria-label={`Select finding ${finding.risk_category}`}
            />
            <span>Select</span>
          </label>
        )}
      </div>

      <div className="finding-card-body">
        <div className="finding-quote">
          <div className="source-label">
            <FileText size={13} /> Original contract text
          </div>
          <blockquote>
            {finding.contract_quote
              ? truncate(finding.contract_quote, compact ? 220 : 420)
              : "No contract quotation was captured for this finding."}
          </blockquote>
        </div>

        <div className="finding-explanation">
          <div className="source-label source-label-model">
            <Sparkles size={13} /> Model-generated explanation
          </div>
          <p>{truncate(finding.explanation, compact ? 180 : 320)}</p>
        </div>
      </div>

      <div className="finding-card-meta">
        <span className="meta-item">
          <ShieldAlert size={13} />
          {finding.finding_type.replace(/_/g, " ")}
        </span>
        <span className="meta-item">
          <MapPin size={13} />
          {page ? `Contract page ${page}` : "Page reference unavailable"}
        </span>
        {finding.policy_source_reference && (
          <span className="meta-item meta-mono">{finding.policy_source_reference}</span>
        )}
        <span className="meta-item">Validation attempts: {finding.validation_attempts}</span>
      </div>

      <div className="finding-card-footer">
        <Link className="text-link" to={detailPath}>
          View finding details <ArrowUpRight size={14} />
        </Link>
        <Link className="text-link muted-link" to={sourcePath}>
          Open cited contract location
        </Link>
      </div>
    </article>
  );
};
