import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  KeyRound,
  LockKeyhole,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2,
  UserRound,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { ToneBadge } from "../components/ui/StatusBadge";
import { ErrorState, LoadingState, Notice, PageHeader } from "../components/ui/States";
import { apiClient } from "../services/apiClient";
import {
  getReviewerAuth,
  saveReviewerAuth,
  subscribeReviewerAuth,
} from "../services/session";
import type { ReadyHealthResponse } from "../types/api";
import { titleCase } from "../utils/format";

export const SettingsPage: React.FC = () => {
  const initialAuth = getReviewerAuth();
  const [reviewerId, setReviewerId] = useState(initialAuth?.reviewerId || "");
  const [apiKey, setApiKey] = useState(initialAuth?.apiKey || "");
  const [saved, setSaved] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [health, setHealth] = useState<ReadyHealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      setHealth(await apiClient.getReadyHealth());
    } catch (error: unknown) {
      setHealthError(error instanceof Error ? error.message : "Readiness check failed.");
    } finally {
      setHealthLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  useEffect(() => {
    return subscribeReviewerAuth(() => {
      const auth = getReviewerAuth();
      setReviewerId(auth?.reviewerId || "");
      setApiKey(auth?.apiKey || "");
    });
  }, []);

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    setSaved(null);
    setSaveError(null);
    if (!reviewerId.trim() || !apiKey.trim()) {
      setSaveError("Both reviewer ID and workflow API key are required.");
      return;
    }
    saveReviewerAuth({ reviewerId, apiKey });
    setSaved("Reviewer credentials saved locally for this browser session store.");
  };

  const clear = () => {
    setSaved(null);
    setSaveError(null);
    saveReviewerAuth(null);
    setReviewerId("");
    setApiKey("");
    setSaved("Saved credentials removed. Development fallback credentials may still apply.");
  };

  return (
    <div id="settings-page">
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description="Configure the reviewer identity used by protected workflow endpoints and inspect backend readiness."
        actions={
          <Button
            variant="secondary"
            onClick={() => void loadHealth()}
            disabled={healthLoading}
            icon={<RefreshCw size={14} className={healthLoading ? "spin" : ""} />}
          >
            Recheck backend
          </Button>
        }
      />

      <div className="settings-grid">
        <Card
          id="card-settings-auth"
          title="Reviewer authentication"
          subtitle="Sent as X-Reviewer-ID and X-Workflow-Key on protected workflow requests"
        >
          <form onSubmit={save} className="stack-form">
            <label className="field">
              <span><UserRound size={14} /> Reviewer ID</span>
              <input
                type="text"
                autoComplete="username"
                value={reviewerId}
                onChange={(event) => setReviewerId(event.target.value)}
                placeholder="e.g. local-reviewer"
              />
            </label>
            <label className="field">
              <span><KeyRound size={14} /> Workflow API key</span>
              <input
                type="password"
                autoComplete="current-password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="Enter your workflow API key"
              />
            </label>
            <div className="inline-actions">
              <Button type="submit" icon={<LockKeyhole size={15} />}>
                Save reviewer credentials
              </Button>
              <Button type="button" variant="secondary" onClick={clear} icon={<Trash2 size={14} />}>
                Remove saved credentials
              </Button>
            </div>
            {saveError && <Notice tone="danger" title="Credentials not saved">{saveError}</Notice>}
            {saved && <Notice tone="success" title="Reviewer session updated">{saved}</Notice>}
          </form>
          <div className="card-divider" />
          <p className="muted-text">
            Credentials are stored in browser local storage for local deployment. Use a
            deployment-level identity provider before exposing this app outside a trusted
            environment. API keys are never sent to the browser via environment variables in
            production builds.
          </p>
        </Card>

        <Card
          id="card-settings-health"
          title="Backend readiness"
          subtitle="Live readiness response from /api/v1/health/ready"
          action={
            health ? (
              <ToneBadge tone={health.status === "healthy" ? "success" : health.status === "degraded" ? "warning" : "danger"}>
                {titleCase(health.status)}
              </ToneBadge>
            ) : undefined
          }
        >
          {healthLoading ? (
            <LoadingState label="Checking backend readiness…" compact />
          ) : healthError ? (
            <ErrorState message={healthError} onRetry={() => void loadHealth()} compact />
          ) : health ? (
            <>
              <div className="detail-grid">
                <div><span>Service</span><strong>{health.app}</strong></div>
                <div><span>Version</span><strong>{health.version}</strong></div>
                <div><span>Environment</span><strong>{health.environment}</strong></div>
                <div><span>Checked</span><strong>{new Date(health.timestamp).toLocaleString()}</strong></div>
              </div>
              <div className="card-divider" />
              <div className="health-components">
                {Object.entries(health.components).map(([name, component]) => (
                  <div className="health-component" key={name}>
                    <div className="health-component-head">
                      <span>{titleCase(name)}</span>
                      <ToneBadge tone={component.status === "healthy" ? "success" : component.status === "degraded" ? "warning" : "danger"}>
                        {component.status}
                      </ToneBadge>
                    </div>
                    {component.details && <p className="table-secondary">{component.details}</p>}
                    {component.latency_ms !== undefined && (
                      <span className="table-secondary">{component.latency_ms.toFixed(0)} ms</span>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </Card>
      </div>

      <div className="settings-grid">
        <Card id="card-settings-api" title="Backend configuration" subtitle="Runtime defaults for local development">
          <div className="detail-list">
            <div><span>Application</span><strong>ContractGuard Backend</strong></div>
            <div><span>API base URL</span><code>{import.meta.env.VITE_API_BASE_URL || "same-origin / Vite proxy"}</code></div>
            <div><span>Swagger docs</span><a className="text-link" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">/docs</a></div>
            <div><span>Frontend origin</span><code>{typeof window !== "undefined" ? window.location.origin : "—"}</code></div>
          </div>
        </Card>

        <Card id="card-settings-ai" title="AI and vector services" subtitle="Subsystems verified by readiness checks">
          <div className="detail-list">
            <div><span>LLM provider</span><strong>Gemini via abstraction layer</strong></div>
            <div><span>Configured model</span><code>GEMINI_MODEL</code></div>
            <div><span>Vector storage</span><strong>Qdrant</strong></div>
            <div><span>Secrets</span><span className="inline-note"><ShieldCheck size={14} /> Backend environment only</span></div>
          </div>
          <div className="card-divider" />
          <p className="muted-text">
            <Server size={14} /> Readiness values come from the live backend and are not
            hardcoded status indicators.
          </p>
        </Card>
      </div>

      <Card id="card-settings-privacy" title="Evidence handling" subtitle="Review safety rules">
        <ul className="plain-list">
          <li><CheckCircle2 size={15} /> Unverified findings are never presented as verified evidence.</li>
          <li><CheckCircle2 size={15} /> Model explanations are labelled separately from contract quotations.</li>
          <li><CheckCircle2 size={15} /> Reviewer decisions are recorded with reviewer identity and timestamps.</li>
          <li><CheckCircle2 size={15} /> ContractGuard does not perform external legal actions.</li>
        </ul>
      </Card>
    </div>
  );
};
