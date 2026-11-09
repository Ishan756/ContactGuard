import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BookOpen,
  FileUp,
  Plus,
  RefreshCw,
  Search,
  UploadCloud,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { ToneBadge } from "../components/ui/StatusBadge";
import {
  EmptyState,
  LoadingState,
  Notice,
  PageHeader,
  Pagination,
  ProgressBar,
} from "../components/ui/States";
import { apiClient, ApiClientError } from "../services/apiClient";
import type {
  PolicyResponse,
  PolicySearchResultItem,
  PolicyStatus,
} from "../types/api";
import { formatBytes, formatDate } from "../utils/format";

type AddMode = "text" | "file";
const PAGE_SIZE = 20;

function statusTone(status: PolicyStatus) {
  if (status === "active") return "success" as const;
  if (status === "draft") return "warning" as const;
  return "neutral" as const;
}

export const PolicyLibraryPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const highlightedPolicyId = searchParams.get("policy");
  const fileRef = useRef<HTMLInputElement>(null);
  const [policies, setPolicies] = useState<PolicyResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<AddMode>("text");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [category, setCategory] = useState("Liability");
  const [description, setDescription] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [query, setQuery] = useState("");
  const [searchCategory, setSearchCategory] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<PolicySearchResultItem[]>([]);
  const [searchNote, setSearchNote] = useState<string | null>(null);

  const loadPolicies = useCallback(async (targetPage: number = page) => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.listPolicies(
        PAGE_SIZE,
        (targetPage - 1) * PAGE_SIZE,
        statusFilter === "all" ? {} : { status: statusFilter }
      );
      setPolicies(response.policies);
      setTotal(response.total);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Unable to load policies.");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    void loadPolicies(page);
  }, [loadPolicies, page]);

  const selectFile = (selected: File | null) => {
    setError(null);
    if (!selected) {
      setFile(null);
      return;
    }
    const extension = selected.name.split(".").pop()?.toLowerCase();
    if (!extension || !["pdf", "docx"].includes(extension)) {
      setError("Policy documents must be PDF or DOCX files.");
      return;
    }
    if (selected.size > 25 * 1024 * 1024) {
      setError(`Policy file must be 25 MB or smaller (selected ${formatBytes(selected.size)}).`);
      return;
    }
    setFile(selected);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      if (mode === "text") {
        if (!name.trim() || !text.trim()) {
          setError("Policy name and rules text are required.");
          return;
        }
        await apiClient.createPolicy({
          name: name.trim(),
          version: version.trim() || "1.0.0",
          category: category.trim() || null,
          description: description.trim() || null,
          text_content: text.trim(),
        });
        setSuccess(`Policy "${name.trim()}" created and vectorized.`);
        setText("");
      } else {
        if (!name.trim() || !file) {
          setError("Policy name and a PDF/DOCX file are required.");
          return;
        }
        await apiClient.uploadPolicyDocument(
          {
            name: name.trim(),
            version: version.trim() || "1.0.0",
            category: category.trim() || undefined,
            description: description.trim() || undefined,
          },
          file
        );
        setSuccess(`Policy "${name.trim()}" uploaded and indexed.`);
        setFile(null);
        if (fileRef.current) fileRef.current.value = "";
      }
      setName("");
      setDescription("");
      await loadPolicies(1);
      setPage(1);
    } catch (error: unknown) {
      setError(
        error instanceof ApiClientError ? error.message : "Unable to create the policy."
      );
    } finally {
      setBusy(false);
    }
  };

  const searchPolicies = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setSearchNote(null);
    try {
      const response = await apiClient.searchPolicies(
        query.trim(),
        searchCategory.trim() || undefined,
        8
      );
      setSearchResults(response.results);
      setSearchNote(
        response.results[0]?.factual_confidence_note ||
          "Similarity indicates semantic closeness, not legal compliance."
      );
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Policy search failed.");
    } finally {
      setSearching(false);
    }
  };

  const selectedPolicy = policies.find((policy) => policy.id === highlightedPolicyId);

  return (
    <div id="policies-page">
      <PageHeader
        eyebrow="Knowledge base"
        title="Policy library"
        description="Upload and version company policies, monitor vector-indexing status, and test semantic retrieval against contract language."
        actions={
          <Button
            variant="secondary"
            onClick={() => void loadPolicies(page)}
            disabled={loading}
            icon={<RefreshCw size={14} className={loading ? "spin" : ""} />}
          >
            Refresh
          </Button>
        }
      />

      {error && <Notice tone="danger" title="Policy operation failed">{error}</Notice>}
      {success && <Notice tone="success" title="Policy updated">{success}</Notice>}
      {busy && <ProgressBar label="Indexing policy and embeddings" indeterminate />}

      {selectedPolicy && (
        <Notice tone="info" title="Policy referenced by finding">
          {selectedPolicy.name} · v{selectedPolicy.version} · {selectedPolicy.total_chunks} indexed
          chunks.
        </Notice>
      )}

      <Card
        id="card-clause-retrieval"
        title="Semantic policy retrieval"
        subtitle="Retrieve relevant policy passages for a sample contract clause"
        style={{ marginBottom: "1.25rem" }}
      >
        <form onSubmit={searchPolicies} className="stack-form">
          <label className="field">
            <span>Contract clause or question</span>
            <textarea
              id="clause-search-input"
              rows={3}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. Liability is capped at fees paid in the previous 12 months."
            />
          </label>
          <div className="inline-form-row">
            <label className="field">
              <span>Category filter (optional)</span>
              <input
                type="text"
                value={searchCategory}
                onChange={(event) => setSearchCategory(event.target.value)}
                placeholder="e.g. Liability"
              />
            </label>
            <div className="field field-align-end">
              <Button type="submit" disabled={searching || !query.trim()} icon={<Search size={15} />}>
                {searching ? "Searching…" : "Retrieve policy evidence"}
              </Button>
            </div>
          </div>
        </form>

        {searchResults.length > 0 && (
          <div className="search-results">
            <div className="section-heading">
              <h4>{searchResults.length} passages retrieved</h4>
              {searchNote && <span className="muted-text">{searchNote}</span>}
            </div>
            {searchResults.map((result) => (
              <article className="search-result" key={result.chunk_id}>
                <div className="search-result-head">
                  <div>
                    <strong>{result.policy_name}</strong>
                    <span className="table-secondary">
                      v{result.policy_version}
                      {result.category ? ` · ${result.category}` : ""}
                      {result.section_heading ? ` · ${result.section_heading}` : ""}
                    </span>
                  </div>
                  <ToneBadge tone="success">
                    {(result.similarity_score * 100).toFixed(1)}% similarity
                  </ToneBadge>
                </div>
                <blockquote className="quote-block quote-policy">{result.text}</blockquote>
                <div className="citation-meta">
                  <span>{result.source_identifier}</span>
                  <span>Page {result.page_number}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </Card>

      <div className="policy-grid">
        <Card
          id="card-policies-list"
          title="Indexed policies"
          subtitle={`${total} policies in the knowledge base`}
          action={
            <label className="field field-inline field-compact">
              <span>Status</span>
              <select
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value);
                  setPage(1);
                }}
              >
                <option value="all">All</option>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="archived">Archived</option>
              </select>
            </label>
          }
        >
          {loading ? (
            <LoadingState label="Loading policies…" compact />
          ) : policies.length === 0 ? (
            <EmptyState
              icon={<BookOpen size={26} />}
              title="No policies found"
              description="Create a text policy or upload a PDF/DOCX policy document."
            />
          ) : (
            <>
              <div className="policy-list">
                {policies.map((policy) => (
                  <article
                    className={`policy-row ${policy.id === highlightedPolicyId ? "policy-row-highlight" : ""}`}
                    key={policy.id}
                  >
                    <div className="policy-row-main">
                      <div className="policy-row-title">
                        <BookOpen size={16} />
                        <strong>{policy.name}</strong>
                        <ToneBadge tone={statusTone(policy.status)}>{policy.status}</ToneBadge>
                      </div>
                      <div className="table-secondary">
                        v{policy.version} · {policy.category || "General"} · {policy.total_chunks} chunks
                      </div>
                      {policy.description && <p>{policy.description}</p>}
                      <div className="citation-meta">
                        Updated {formatDate(policy.updated_at)}
                        {policy.source_document_id ? ` · Source document ${policy.source_document_id.slice(0, 10)}` : ""}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
              {total > PAGE_SIZE && (
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={total}
                  label="policies"
                  onPageChange={setPage}
                />
              )}
            </>
          )}
        </Card>

        <Card
          id="card-add-policy"
          title="Add policy"
          subtitle="Create a text policy or upload a policy document"
          action={
            <div className="segmented-control" role="tablist" aria-label="Policy input mode">
              <button
                type="button"
                role="tab"
                aria-selected={mode === "text"}
                className={mode === "text" ? "active" : ""}
                onClick={() => setMode("text")}
              >
                Text
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === "file"}
                className={mode === "file" ? "active" : ""}
                onClick={() => setMode("file")}
              >
                File
              </button>
            </div>
          }
        >
          <form onSubmit={submit} className="stack-form">
            <label className="field">
              <span>Policy name</span>
              <input
                type="text"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Standard vendor indemnity rule"
              />
            </label>
            <div className="inline-form-row">
              <label className="field">
                <span>Version</span>
                <input
                  type="text"
                  value={version}
                  onChange={(event) => setVersion(event.target.value)}
                  placeholder="1.0.0"
                />
              </label>
              <label className="field">
                <span>Category</span>
                <input
                  type="text"
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                  placeholder="Liability"
                />
              </label>
            </div>
            <label className="field">
              <span>Description (optional)</span>
              <input
                type="text"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Purpose or scope of this policy"
              />
            </label>

            {mode === "text" ? (
              <label className="field">
                <span>Policy rules text</span>
                <textarea
                  required
                  rows={7}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="SECTION 1. LIABILITY CAP. All vendor contracts must include an aggregate liability limit..."
                />
              </label>
            ) : (
              <div className="field">
                <span>Policy document</span>
                <div
                  className={`upload-dropzone upload-dropzone-small ${file ? "upload-dropzone-active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => fileRef.current?.click()}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") fileRef.current?.click();
                  }}
                >
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx"
                    className="visually-hidden"
                    onChange={(event) => selectFile(event.target.files?.[0] || null)}
                  />
                  <FileUp size={22} />
                  <span>{file ? file.name : "Choose a PDF or DOCX policy document"}</span>
                  <small>Maximum 25 MB</small>
                </div>
              </div>
            )}

            <Button type="submit" disabled={busy} icon={mode === "file" ? <UploadCloud size={15} /> : <Plus size={15} />}>
              {busy ? "Saving and indexing…" : mode === "file" ? "Upload and vectorize policy" : "Save and vectorize policy"}
            </Button>
          </form>
        </Card>
      </div>

      {searchResults.length === 0 && query && !searching && (
        <p className="muted-text">
          No matching policy passages were returned for this query.
        </p>
      )}
    </div>
  );
};
