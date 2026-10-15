import React, { useEffect, useRef, useState } from "react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { apiClient, ApiClientError } from "../services/apiClient";
import type {
  DocumentMetadataResponse,
  DocumentStatus,
  DocumentTextResponse,
} from "../types/api";
import {
  FileUp,
  AlertCircle,
  FileText,
  X,
  RefreshCw,
  Hash,
  Eye,
} from "lucide-react";

export const AuditQueuePage: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentMetadataResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState<boolean>(false);

  // Document Chunk Inspector Drawer
  const [selectedDoc, setSelectedDoc] = useState<DocumentMetadataResponse | null>(null);
  const [docChunks, setDocChunks] = useState<DocumentTextResponse | null>(null);
  const [chunksLoading, setChunksLoading] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    setIsLoading(true);
    try {
      const resp = await apiClient.listDocuments(50, 0);
      setDocuments(resp.documents);
    } catch {
      // In initial mock or offline state
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileValidationAndUpload = async (file: File) => {
    setUploadError(null);
    setUploadSuccess(null);

    // Client-side extension validation
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["pdf", "docx"].includes(ext)) {
      setUploadError(`Invalid file format '.${ext || "unknown"}'. Only PDF and DOCX files are permitted.`);
      return;
    }

    // Client-side 25MB size limit check
    if (file.size > 25 * 1024 * 1024) {
      setUploadError(`File size (${(file.size / (1024 * 1024)).toFixed(2)}MB) exceeds 25MB upload limit.`);
      return;
    }

    if (file.size === 0) {
      setUploadError("Uploaded file is empty (0 bytes).");
      return;
    }

    setIsUploading(true);
    try {
      const resp = await apiClient.uploadDocument(file);
      setUploadSuccess(`Successfully ingested "${resp.document.original_filename}" (${resp.chunks_extracted} clauses parsed).`);
      await fetchDocuments();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setUploadError(err.message);
      } else {
        setUploadError("An unexpected error occurred during document upload.");
      }
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileValidationAndUpload(e.dataTransfer.files[0]);
    }
  };

  const openInspector = async (doc: DocumentMetadataResponse) => {
    setSelectedDoc(doc);
    setChunksLoading(true);
    try {
      const chunksResp = await apiClient.getDocumentChunks(doc.id, 1, 50);
      setDocChunks(chunksResp);
    } catch {
      setDocChunks(null);
    } finally {
      setChunksLoading(false);
    }
  };

  const getStatusBadge = (status: DocumentStatus) => {
    switch (status) {
      case "completed":
        return <Badge status="healthy">Extracted</Badge>;
      case "needs_ocr":
        return <Badge status="degraded">Needs OCR</Badge>;
      case "failed":
        return <Badge status="unhealthy">Failed</Badge>;
      case "processing":
      case "pending":
      default:
        return <Badge status="neutral">Processing</Badge>;
    }
  };

  return (
    <div id="audit-queue-page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Contract Ingestion & Queue</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            Securely upload PDF/DOCX contracts. Files are isolated outside web roots and parsed with page-aware evidence offsets.
          </p>
        </div>
        <Button
          id="btn-refresh-documents"
          variant="secondary"
          onClick={fetchDocuments}
          disabled={isLoading}
          icon={<RefreshCw size={14} className={isLoading ? "spin" : ""} />}
        >
          Refresh Queue
        </Button>
      </div>

      {/* Upload Zone */}
      <Card id="contract-upload-card" style={{ marginBottom: "1.5rem" }}>
        <div
          id="dropzone-area"
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          style={{
            border: `2px dashed ${dragActive ? "var(--accent-cyan)" : "var(--border-subtle)"}`,
            borderRadius: "var(--radius-lg)",
            padding: "2rem",
            textAlign: "center",
            background: dragActive ? "rgba(6, 182, 212, 0.05)" : "rgba(255, 255, 255, 0.01)",
            transition: "all 0.2s ease",
            cursor: "pointer",
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            id="file-upload-input"
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx"
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files && e.target.files[0]) {
                handleFileValidationAndUpload(e.target.files[0]);
              }
            }}
          />
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: "50%",
                background: "rgba(6, 182, 212, 0.1)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <FileUp size={24} color="var(--accent-cyan)" />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "1rem" }}>
                {isUploading ? "Uploading & extracting document..." : "Click or drag contract file here to ingest"}
              </div>
              <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
                Supported formats: <strong>PDF, DOCX</strong> • Maximum size: <strong>25MB</strong>
              </div>
            </div>
          </div>
        </div>

        {uploadError && (
          <div
            id="upload-error-alert"
            style={{
              marginTop: "1rem",
              padding: "0.75rem 1rem",
              borderRadius: "var(--radius-md)",
              background: "rgba(244, 63, 94, 0.1)",
              border: "1px solid rgba(244, 63, 94, 0.3)",
              color: "var(--accent-rose)",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <AlertCircle size={18} />
            <span>{uploadError}</span>
          </div>
        )}

        {uploadSuccess && (
          <div
            id="upload-success-alert"
            style={{
              marginTop: "1rem",
              padding: "0.75rem 1rem",
              borderRadius: "var(--radius-md)",
              background: "rgba(16, 185, 129, 0.1)",
              border: "1px solid rgba(16, 185, 129, 0.3)",
              color: "#34d399",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <span>{uploadSuccess}</span>
          </div>
        )}
      </Card>

      {/* Uploaded Documents List */}
      <Card id="audit-queue-table-card" title="Ingested Documents" subtitle="Verified repository of contracts">
        {documents.length === 0 && !isLoading ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
            <FileText size={36} style={{ margin: "0 auto 1rem", opacity: 0.5 }} />
            <p>No contracts uploaded yet. Drop a PDF or DOCX agreement above to begin.</p>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" id="audit-contracts-table">
              <thead>
                <tr>
                  <th>Contract Name</th>
                  <th>Format</th>
                  <th>Status</th>
                  <th>Pages</th>
                  <th>Characters</th>
                  <th>SHA-256 Hash</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => {
                  const ext = doc.original_filename.split(".").pop()?.toUpperCase() || "DOC";
                  return (
                    <tr key={doc.id} id={`doc-row-${doc.id}`}>
                      <td style={{ fontWeight: 600 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <FileText size={16} color="var(--accent-cyan)" />
                          <span>{doc.original_filename}</span>
                        </div>
                        {doc.error_message && (
                          <div style={{ fontSize: "0.75rem", color: "var(--accent-amber)", marginTop: "0.2rem" }}>
                            {doc.error_message}
                          </div>
                        )}
                      </td>
                      <td>
                        <Badge status="neutral">{ext}</Badge>
                      </td>
                      <td>{getStatusBadge(doc.status)}</td>
                      <td>{doc.total_pages > 0 ? doc.total_pages : "--"}</td>
                      <td>{doc.total_characters.toLocaleString()}</td>
                      <td>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          {doc.file_hash_sha256.slice(0, 10)}...
                        </span>
                      </td>
                      <td>
                        <Button
                          id={`btn-inspect-${doc.id}`}
                          variant="secondary"
                          onClick={() => openInspector(doc)}
                          icon={<Eye size={14} />}
                          style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }}
                        >
                          Inspect Clauses
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Document Inspector Modal / Drawer */}
      {selectedDoc && (
        <div
          id="document-inspector-modal"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: "2rem",
          }}
        >
          <div
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-xl)",
              width: "100%",
              maxWidth: "900px",
              maxHeight: "90vh",
              display: "flex",
              flexDirection: "column",
              boxShadow: "0 20px 40px rgba(0, 0, 0, 0.8)",
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: "1.5rem",
                borderBottom: "1px solid var(--border-subtle)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <h3 style={{ fontSize: "1.25rem", fontWeight: 700 }}>{selectedDoc.original_filename}</h3>
                  {getStatusBadge(selectedDoc.status)}
                </div>
                <div style={{ display: "flex", gap: "1.5rem", marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  <span>ID: <code style={{ color: "var(--text-secondary)" }}>{selectedDoc.id}</code></span>
                  <span>Pages: <strong>{selectedDoc.total_pages}</strong></span>
                  <span>Characters: <strong>{selectedDoc.total_characters}</strong></span>
                </div>
                <div style={{ marginTop: "0.25rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  <Hash size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: "4px" }} />
                  SHA-256: <code style={{ color: "var(--text-secondary)" }}>{selectedDoc.file_hash_sha256}</code>
                </div>
              </div>
              <button
                id="btn-close-inspector"
                onClick={() => setSelectedDoc(null)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  padding: "0.4rem",
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Body: Clause Chunks */}
            <div style={{ padding: "1.5rem", overflowY: "auto", flex: 1 }}>
              {selectedDoc.status === "needs_ocr" && (
                <div
                  style={{
                    padding: "1rem",
                    marginBottom: "1rem",
                    borderRadius: "var(--radius-md)",
                    background: "rgba(245, 158, 11, 0.1)",
                    border: "1px solid rgba(245, 158, 11, 0.3)",
                    color: "var(--accent-amber)",
                    fontSize: "0.85rem",
                  }}
                >
                  <strong>OCR Required:</strong> This document was flagged as a scanned or image-based agreement with insufficient text layer.
                  Full clause analysis requires OCR integration.
                </div>
              )}

              {chunksLoading ? (
                <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}>
                  Loading extracted clauses...
                </div>
              ) : docChunks?.chunks.length === 0 ? (
                <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}>
                  No extractable clauses detected.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {docChunks?.chunks.map((chunk) => (
                    <div
                      key={chunk.id}
                      style={{
                        padding: "1rem",
                        borderRadius: "var(--radius-md)",
                        background: "rgba(255, 255, 255, 0.02)",
                        border: "1px solid var(--border-subtle)",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: "0.5rem",
                          borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                          paddingBottom: "0.4rem",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <Badge status="neutral">Page {chunk.page_number}</Badge>
                          {chunk.section_heading && (
                            <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--accent-cyan)" }}>
                              {chunk.section_heading}
                            </span>
                          )}
                        </div>
                        <span style={{ fontSize: "0.75rem", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                          offset: [{chunk.start_char_offset} - {chunk.end_char_offset}]
                        </span>
                      </div>
                      <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                        {chunk.text}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
