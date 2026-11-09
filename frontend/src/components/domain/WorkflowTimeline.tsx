import React from "react";
import { CheckCircle2, CircleDot, Clock3, XCircle } from "lucide-react";
import type { WorkflowEventResponse, WorkflowRunResponse } from "../../types/api";
import { formatDate, titleCase } from "../../utils/format";
import { DecisionBadge } from "../ui/StatusBadge";

function eventIcon(event: WorkflowEventResponse) {
  if (event.event_type === "failed") return <XCircle size={15} />;
  if (event.event_type === "completed") return <CheckCircle2 size={15} />;
  if (event.event_type === "interrupted") return <Clock3 size={15} />;
  return <CircleDot size={15} />;
}

export const WorkflowTimeline: React.FC<{ workflow: WorkflowRunResponse }> = ({ workflow }) => (
  <div className="workflow-history">
    <section>
      <h4>Execution events</h4>
      {workflow.events.length === 0 ? (
        <p className="muted-text">No workflow events recorded yet.</p>
      ) : (
        <ol className="timeline">
          {workflow.events.map((event) => (
            <li key={event.event_id} className={`timeline-item timeline-${event.event_type}`}>
              <span className="timeline-icon" aria-hidden="true">
                {eventIcon(event)}
              </span>
              <div>
                <div className="timeline-title">
                  {titleCase(event.event_type)}
                  {event.node && <span className="timeline-node"> · {event.node}</span>}
                </div>
                {event.message && <p>{event.message}</p>}
                <div className="timeline-meta">
                  {formatDate(event.created_at)}
                  {event.status_to && ` · ${titleCase(event.status_to)}`}
                  {event.actor_id && ` · ${event.actor_id}`}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>

    <section>
      <h4>Reviewer decisions</h4>
      {workflow.decisions.length === 0 ? (
        <p className="muted-text">No human decisions recorded for this run.</p>
      ) : (
        <div className="decision-list">
          {workflow.decisions.map((decision) => (
            <div className="decision-item" key={decision.decision_id}>
              <div className="decision-item-head">
                <DecisionBadge decision={decision.decision} />
                <span>{formatDate(decision.created_at)}</span>
              </div>
              <div className="muted-text">Reviewer: {decision.reviewer_id}</div>
              {decision.notes && <p>{decision.notes}</p>}
              {decision.revision_instructions && (
                <p>
                  <strong>Revision instructions:</strong> {decision.revision_instructions}
                </p>
              )}
              {decision.finding_ids.length > 0 && (
                <div className="muted-text">{decision.finding_ids.length} finding(s) selected</div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  </div>
);
