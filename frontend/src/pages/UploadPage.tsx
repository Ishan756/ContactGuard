import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  FileText,
  FileUp,
  Hash,
  RefreshCw,
  UploadCloud,
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
  Pagination,
  ProgressBar,
} from "../components/ui/States";
import { apiClient, ApiClientError } from "../services/apiClient";
import type { DocumentMetadataResponse, DocumentUploadResponse } from "../types/api";
import { formatBytes, formatDate, titleCase } from "../utils/format";

type UploadStage = "idle" | "validating" | "uploading" | "extracting" | "complete" | "error";

const PAGE_SIZE = 10;

function validateFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !["pdf", "docx"].includes(extension)) {
    return `Invalid file format '.${extension || "unknown"}'. Only PDF and DOCX files are permitted.`;
  }
  if (file.size === 0) {
    return "Uploaded file is empty (0 bytes).";
  }
  if (file.size > 25 * 1024 * 1024) {
    return `File size (${formatBytes(file.size)}) exceeds the 25 MB upload limit.`;
  }
  return null;
}

export const UploadPage: React.FC = () => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<DocumentMetadataResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [stage, setStage] = useState<UploadStage>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<DocumentUploadResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const loadDocuments = useCallback(async (targetPage: number = page) => {
    setLoading(true);
    setListError(null);
    try {
      const response = await apiClient.listDocuments(PAGE_SIZE, (targetPage - 1) * PAGE_SIZE);
      setDocuments(response.documents);
      setTotal(response.total);
      setSelectedId((current) => current || response.documents[0]?.id || null);
    } catch (error: unknown) {
      setListError(error instanceof Error ? error.message : "Unable to load documents.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void loadDocuments(page);
  }, [loadDocuments, page]);

  const handleFile = async (file: File) => {
    setUploadError(null);
    setUploaded(null);
    setStage("validating");
    const validationError = validateFile(file);
    if (validationError) {
      setUploadError(validationError);
      setStage("error");
      return;
    }

    setStage("uploading");
    try {
      const response = await apiClient.uploadDocument(file);
      setStage("extracting");
      setUploaded(response);
      setStage("complete");
      setSelectedId(response.document.id);
      await loadDocuments(documents.length === PAGE_SIZE ? 1 : page);
      if (inputRef.current) inputRef.current.value = "";
    } catch (error: unknown) {
      setUploadError(
        error instanceof ApiClientError
          ? error.message
          : "An unexpected error occurred during document upload."
      );
      setStage("error");
    }
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  };

  const selectedDocument = documents.find((document) => document.id === selectedId) || null;
  const progress =
    stage === "validating"
      ? 8
      : stage === "uploading"
        ? 35
        : stage === "extracting"
          ? 82
          : stage === "complete"
            ? 100
            : 0;
  const isBusy = stage === "validating" || stage === "uploading" || stage === "extracting";

  return (
    <div id="upload-page">
      <PageHeader
        eyebrow="Document intake"
        title="Upload contracts"
        description="Securely ingest PDF and DOCX agreements, validate file integrity, and start a review once text extraction completes."
        actions={
          <Button
            variant="secondary"
            onClick={() => void loadDocuments(page)}
            disabled={loading}
            icon={<RefreshCw size={14} className={loading ? "spin" : ""} />}
          >
            Refresh
          </Button>
        }
      />

      <Card id="contract-upload-card" style={{ marginBottom: "1.5rem" }}>
        <div
          id="dropzone-area"
          role="button"
          tabIndex={0}
          aria-label="Upload a PDF or DOCX contract"
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              inputRef.current?.click();
            }
          }}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            setDragActive(false);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`upload-dropzone ${dragActive ? "upload-dropzone-active" : ""}`}
        >
          <input
            id="file-upload-input"
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="visually-hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
          <span className="upload-dropzone-icon">
            <FileUp size={26} />
          </span>
          <div>
            <div className="upload-dropzone-title">
              {isBusy ? "Processing contract…" : "Drop a contract here or browse files"}
            </div>
            <div className="upload-dropzone-note">
              PDF or DOCX · maximum 25 MB · files are stored outside the web root
            </div>
          </div>
        </div>

        {(isBusy || stage === "complete") && (
          <div className="upload-progress">
            <ProgressBar
              value={progress}
              label={
                stage === "validating"
                  ? "Validating file"
                  : stage === "uploading"
                    ? "Uploading document"
                    : stage === "extracting"
                      ? "Extracting page-aware text"
                      : "Upload and extraction complete"
              }
              indeterminate={isBusy && stage === "extracting"}
              tone={stage === "complete" ? "emerald" : "cyan"}
            />
          </div>
        )}

        {uploadError && (
          <Notice tone="danger" title="Upload failed">
            {uploadError}
          </Notice>
        )}

        {uploaded && stage === "complete" && (
          <Notice tone="success" title="Contract ingested">
            <div className="upload-success-row">
              <span>
                <strong>{uploaded.document.original_filename}</strong> ·{" "}
                {uploaded.chunks_extracted} text chunks extracted. {uploaded.message}
              </span>
              <Link className="text-link" to={`/contracts/${uploaded.document.id}/review`}>
                Open review <ArrowRight size={14} />
              </Link>
            </div>
          </Notice>
        )}
      </Card>

      {selectedDocument && (
        <Card
          id="selected-document-card"
          title="Selected contract"
          subtitle="Confirm extraction status before opening the review workspace"
          action={
            selectedDocument.status === "completed" ? (
              <Link className="btn btn-primary" to={`/contracts/${selectedDocument.id}/review`}>
                Review contract <ArrowRight size={15} />
              </Link>
            ) : undefined
          }
          style={{ marginBottom: "1.5rem" }}
        >
          <div className="selected-document">
            <div className="selected-document-main">
              <div className="selected-document-icon"><FileText size={22} /></div>
              <div>
                <h3>{selectedDocument.original_filename}</h3>
                <div className="table-secondary">
                  {formatBytes(selectedDocument.file_size_bytes)} ·{" "}
                  {selectedDocument.total_pages || "—"} pages ·{" "}
                  {selectedDocument.total_characters.toLocaleString()} characters
                </div>
                <div className="hash-line">
                  <Hash size={12} /> {selectedDocument.file_hash_sha256}
                </div>
              </div>
            </div>
            <ToneBadge
              tone={
                selectedDocument.status === "completed"
                  ? "success"
                  : selectedDocument.status === "failed"
                    ? "danger"
                    : "warning"
              }
            >
              {titleCase(selectedDocument.status)}
            </ToneBadge>
          </div>
          {selectedDocument.status !== "completed" && (
            <Notice tone="warning">
              This document is not ready for review. Status: {titleCase(selectedDocument.status)}.
              {selectedDocument.error_message ? ` ${selectedDocument.error_message}` : ""}
            </Notice>
          )}
        </Card>
      )}

      <Card
        id="audit-queue-table-card"
        title="Contract library"
        subtitle={`${total} uploaded documents`}
      >
        {loading ? (
          <LoadingState label="Loading contracts…" compact />
        ) : listError ? (
          <ErrorState message={listError} onRetry={() => void loadDocuments(page)} compact />
        ) : documents.length === 0 ? (
          <EmptyState
            icon={<UploadCloud size={28} />}
            title="No contracts uploaded"
            description="Upload a PDF or DOCX agreement to begin extraction and review."
            action={<Button onClick={() => inputRef.current?.click()}>Choose a file</Button>}
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table" id="audit-contracts-table">
                <thead>
                  <tr>
                    <th>Contract</th>
                    <th>Status</th>
                    <th>Pages</th>
                    <th>Characters</th>
                    <th>Uploaded</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((document) => (
                    <tr
                      key={document.id}
                      className={document.id === selectedId ? "table-row-selected" : ""}
                      onClick={() => setSelectedId(document.id)}
                    >
                      <td>
                        <div className="table-primary">
                          <FileText size={15} /> {document.original_filename}
                        </div>
                        {document.error_message && (
                          <div className="table-warning">{document.error_message}</div>
                        )}
                      </td>
                      <td>
                        <ToneBadge
                          tone={
                            document.status === "completed"
                              ? "success"
                              : document.status === "failed"
                                ? "danger"
                                : "warning"
                          }
                        >
                          {titleCase(document.status)}
                        </ToneBadge>
                      </td>
                      <td>{document.total_pages || "—"}</td>
                      <td>{document.total_characters.toLocaleString()}</td>
                      <td>{formatDate(document.created_at)}</td>
                      <td>
                        <div className="table-actions">
                          <Button
                            variant="secondary"
                            className="btn-small"
                            onClick={(event) => {
                              event.stopPropagation();
                              setSelectedId(document.id);
                            }}
                          >
                            Select
                          </Button>
                          <Link
                            className="text-link"
                            to={`/contracts/${document.id}/review`}
                            onClick={(event) => event.stopPropagation()}
                          >
                            Review <ArrowRight size={14} />
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={total}
              label="contracts"
              onPageChange={(nextPage) => {
                setPage(nextPage);
                setSelectedId(null);
              }}
            />
          </>
        )}
      </Card>

    </div>
  );
};
