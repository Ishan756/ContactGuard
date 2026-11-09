import React from "react";
import type { Tone } from "../../utils/format";
import {
  decisionTone,
  reviewTone,
  severityTone,
  validationLabel,
  validationTone,
  workflowStatusLabel,
  workflowTone,
} from "../../utils/format";
import type {
  ReviewDecisionType,
  ReviewStatus,
  RiskPriority,
  ValidationStatus,
  WorkflowStatus,
} from "../../types/api";

interface ToneBadgeProps {
  tone?: Tone;
  children: React.ReactNode;
  id?: string;
  className?: string;
}

export const ToneBadge: React.FC<ToneBadgeProps> = ({
  tone = "neutral",
  children,
  id,
  className = "",
}) => (
  <span id={id} className={`tone-badge tone-${tone} ${className}`.trim()}>
    {children}
  </span>
);

export const SeverityBadge: React.FC<{ severity: RiskPriority }> = ({ severity }) => (
  <ToneBadge tone={severityTone(severity)}>{severity}</ToneBadge>
);

export const ValidationBadge: React.FC<{ status: ValidationStatus }> = ({ status }) => (
  <ToneBadge tone={validationTone(status)}>{validationLabel(status)}</ToneBadge>
);

export const ReviewBadge: React.FC<{ status: ReviewStatus }> = ({ status }) => (
  <ToneBadge tone={reviewTone(status)}>{status.replace(/_/g, " ")}</ToneBadge>
);

export const WorkflowStatusBadge: React.FC<{ status: WorkflowStatus }> = ({ status }) => (
  <ToneBadge tone={workflowTone(status)}>{workflowStatusLabel(status)}</ToneBadge>
);

export const DecisionBadge: React.FC<{ decision: ReviewDecisionType }> = ({ decision }) => (
  <ToneBadge tone={decisionTone(decision)}>{decision.replace(/_/g, " ")}</ToneBadge>
);
