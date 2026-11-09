import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, FilterX, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
} from "../components/ui/States";
import { FindingCard } from "../components/domain/FindingCard";
import { apiClient } from "../services/apiClient";
import type {
  DocumentMetadataResponse,
  ReviewStatus,
  RiskFindingResponse,
  RiskPriority,
  ValidationStatus,
} from "../types/api";
import { severityOrder } from "../utils/format";

type SortKey = "severity" | "newest" | "category";
const PAGE_SIZE = 8;
const severityOptions: RiskPriority[] = ["critical", "high", "medium", "low", "informational"];
const validationOptions: ValidationStatus[] = [
  "verified",
  "unverified",
  "needs_review",
  "missing_evidence",
  "inconclusive",
  "pending",
];
const reviewOptions: ReviewStatus[] = ["needs_review", "reviewed", "dismissed"];

export const FindingsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const requestedDocument = searchParams.get("document");
  const [documents, setDocuments] = useState<DocumentMetadataResponse[]>([]);
  const [documentId, setDocumentId] = useState(requestedDocument || "");
  const [findings, setFindings] = useState<RiskFindingResponse[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");
  const [category, setCategory] = useState("all");
  const [validation, setValidation] = useState("all");
  const [review, setReview] = useState("all");
  const [sort, setSort] = useState<SortKey>("severity");
  const [page, setPage] = useState(1);

  const loadDocuments = useCallback(async () => {
    setLoadingDocuments(true);
    setError(null);
    try {
      const response = await apiClient.listDocuments(100, 0);
      setDocuments(response.documents);
      setDocumentId((current) => current || response.documents[0]?.id || "");
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Unable to load contracts.");
    } finally {
      setLoadingDocuments(false);
    }
  }, []);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  const loadFindings = useCallback(async () => {
    if (!documentId) {
      setFindings([]);
      return;
    }
    setLoadingFindings(true);
    setError(null);
    try {
      const response = await apiClient.listFindings(documentId, { limit: 500 });
      setFindings(response.findings);
      setPage(1);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Unable to load findings.");
    } finally {
      setLoadingFindings(false);
    }
  }, [documentId]);

  useEffect(() => {
    void loadFindings();
  }, [loadFindings]);

  const categories = useMemo(
    () => Array.from(new Set(findings.map((finding) => finding.risk_category))).sort(),
    [findings]
  );

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return findings
      .filter((finding) => {
        if (severity !== "all" && finding.severity !== severity) return false;
        if (category !== "all" && finding.risk_category !== category) return false;
        if (validation !== "all" && finding.validation_status !== validation) return false;
        if (review !== "all" && finding.review_status !== review) return false;
        if (!needle) return true;
        return [
          finding.risk_category,
          finding.explanation,
          finding.contract_quote || "",
          finding.suggested_question,
          finding.policy_quote || "",
        ]
          .join(" ")
          .toLowerCase()
          .includes(needle);
      })
      .sort((a, b) => {
        if (sort === "newest") {
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        }
        if (sort === "category") {
          return a.risk_category.localeCompare(b.risk_category);
        }
        return severityOrder[a.severity] - severityOrder[b.severity];
      });
  }, [findings, search, severity, category, validation, review, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paged = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const selectedDocument = documents.find((document) => document.id === documentId);
  const resetFilters = () => {
    setSearch("");
    setSeverity("all");
    setCategory("all");
    setValidation("all");
    setReview("all");
    setSort("severity");
    setPage(1);
  };

  const verifiedCount = filtered.filter((finding) => finding.validation_status === "verified").length;
  const unverifiedCount = filtered.filter((finding) => finding.validation_status !== "verified").length;

  return (
    <div id="findings-page">
      <PageHeader
        eyebrow="Evidence review"
        title="Findings"
        description="Filter, sort, and inspect contract quotations, policy citations, validation outcomes, and reviewer state."
        actions={
          <Button
            variant="secondary"
            onClick={() => void loadFindings()}
            disabled={loadingFindings || !documentId}
            icon={<RefreshCw size={14} className={loadingFindings ? "spin" : ""} />}
          >
            Refresh
          </Button>
        }
      />

      <Card style={{ marginBottom: "1rem" }}>
        <div className="findings-toolbar">
          <label className="field field-inline">
            <span>Contract</span>
            <select
              value={documentId}
              onChange={(event) => {
                setDocumentId(event.target.value);
                setPage(1);
              }}
              disabled={loadingDocuments}
            >
              {documents.length === 0 && <option value="">No contracts available</option>}
              {documents.map((document) => (
                <option value={document.id} key={document.id}>
                  {document.original_filename}
                </option>
              ))}
            </select>
          </label>

          <label className="field field-search">
            <span>Search</span>
            <div className="input-with-icon">
              <Search size={15} />
              <input
                type="search"
                placeholder="Search findings, quotes, or questions"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
              />
            </div>
          </label>
        </div>

        <div className="filter-grid">
          <label className="field">
            <span>Severity</span>
            <select value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}>
              <option value="all">All severities</option>
              {severityOptions.map((item) => (
                <option value={item} key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Category</span>
            <select value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }}>
              <option value="all">All categories</option>
              {categories.map((item) => (
                <option value={item} key={item}>{item.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Verification</span>
            <select value={validation} onChange={(event) => { setValidation(event.target.value); setPage(1); }}>
              <option value="all">All verification states</option>
              {validationOptions.map((item) => (
                <option value={item} key={item}>{item.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Review status</span>
            <select value={review} onChange={(event) => { setReview(event.target.value); setPage(1); }}>
              <option value="all">All review states</option>
              {reviewOptions.map((item) => (
                <option value={item} key={item}>{item.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Sort</span>
            <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
              <option value="severity">Severity</option>
              <option value="newest">Newest first</option>
              <option value="category">Category</option>
            </select>
          </label>
          <div className="field field-align-end">
            <Button variant="secondary" onClick={resetFilters} icon={<FilterX size={14} />}>
              Reset
            </Button>
          </div>
        </div>

        <div className="filter-summary">
          <span><strong>{filtered.length}</strong> findings match</span>
          <span className="tone-success"><strong>{verifiedCount}</strong> verified</span>
          <span className="tone-warning"><strong>{unverifiedCount}</strong> need caution</span>
          {selectedDocument && (
            <Link className="text-link" to={`/contracts/${selectedDocument.id}/review`}>
              Open contract review <ArrowRight size={14} />
            </Link>
          )}
        </div>
      </Card>

      {loadingFindings ? (
        <LoadingState label="Loading findings…" />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void loadFindings()} />
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon={<ShieldAlert size={28} />}
            title="No findings match these filters"
            description={
              findings.length === 0
                ? "Run a review workflow or choose another contract."
                : "Adjust filters or clear them to see all findings."
            }
            action={<Button variant="secondary" onClick={resetFilters}>Clear filters</Button>}
          />
        </Card>
      ) : (
        <>
          <div className="findings-list">
            {paged.map((finding) => (
              <FindingCard
                key={finding.finding_id}
                finding={finding}
                documentId={documentId}
              />
            ))}
          </div>
          <Pagination
            page={currentPage}
            pageSize={PAGE_SIZE}
            total={filtered.length}
            label="findings"
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
};
