import React, { useEffect, useMemo, useRef } from "react";
import { FileText, MapPin } from "lucide-react";
import type { DocumentChunkResponse, DocumentMetadataResponse, RiskFindingResponse } from "../../types/api";
import { sourcePage } from "../../utils/format";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";

interface DocumentViewerProps {
  document?: DocumentMetadataResponse | null;
  chunks: DocumentChunkResponse[];
  activePage: number;
  onPageChange: (page: number) => void;
  finding?: RiskFindingResponse | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  document,
  chunks,
  activePage,
  onPageChange,
  finding,
  loading = false,
  error,
  onRetry,
}) => {
  const contentRef = useRef<HTMLDivElement>(null);

  const pages = useMemo(() => {
    const grouped = new Map<number, DocumentChunkResponse[]>();
    chunks.forEach((chunk) => {
      const list = grouped.get(chunk.page_number) || [];
      list.push(chunk);
      grouped.set(chunk.page_number, list);
    });
    return Array.from(grouped.entries()).sort(([a], [b]) => a - b);
  }, [chunks]);

  const selectedPage = sourcePage(
    finding?.contract_source_reference,
    finding?.contract_page_number
  );
  const highlightText = finding?.contract_quote?.trim().slice(0, 90) || "";
  const currentPage = pages.some(([page]) => page === activePage)
    ? activePage
    : pages[0]?.[0] ?? 1;
  const currentChunks = pages.find(([page]) => page === currentPage)?.[1] ?? [];

  useEffect(() => {
    if (selectedPage && selectedPage !== currentPage) {
      onPageChange(selectedPage);
    }
  }, [selectedPage, currentPage, onPageChange]);

  useEffect(() => {
    if (!highlightText || !contentRef.current) return;
    const target = contentRef.current.querySelector<HTMLElement>("[data-source-highlight='true']");
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightText, currentPage]);

  if (loading) {
    return <LoadingState label="Loading contract text…" />;
  }
  if (error) {
    return <ErrorState message={error} onRetry={onRetry} title="Could not load contract text" />;
  }
  if (!document) {
    return <EmptyState title="Select a contract" description="Choose a document to open its source text." />;
  }
  if (chunks.length === 0) {
    return (
      <EmptyState
        icon={<FileText size={28} />}
        title="No extracted text available"
        description="This document may still be processing or may require OCR."
      />
    );
  }

  return (
    <div className="document-viewer" id="document-viewer">
      <div className="document-viewer-header">
        <div>
          <div className="eyebrow">Original contract text</div>
          <h3>{document.original_filename}</h3>
        </div>
        <div className="document-viewer-title-meta">
          <span>{document.total_pages || pages.length} pages</span>
          <span>{chunks.length} indexed passages</span>
        </div>
      </div>

      <div className="document-viewer-grid">
        <nav className="page-rail" aria-label="Contract pages">
          {pages.map(([page, pageChunks]) => (
            <button
              key={page}
              type="button"
              className={`page-rail-button ${page === currentPage ? "active" : ""}`}
              onClick={() => onPageChange(page)}
              aria-current={page === currentPage ? "page" : undefined}
            >
              <span>Page {page}</span>
              <small>{pageChunks.length} passages</small>
            </button>
          ))}
        </nav>

        <div className="document-page" ref={contentRef}>
          <div className="document-page-heading">
            <span className="badge page-badge">Page {currentPage}</span>
            {selectedPage === currentPage && finding && (
              <span className="source-anchor">
                <MapPin size={13} /> Cited by selected finding
              </span>
            )}
          </div>

          {currentChunks.map((chunk) => {
            const highlighted =
              highlightText.length > 12 &&
              chunk.text.replace(/\s+/g, " ").includes(highlightText.replace(/\s+/g, " "));
            return (
              <section
                key={chunk.id}
                className={`document-chunk ${highlighted ? "document-chunk-highlight" : ""}`}
                data-source-highlight={highlighted ? "true" : "false"}
              >
                {chunk.section_heading && <h4>{chunk.section_heading}</h4>}
                <p>{chunk.text}</p>
                <div className="chunk-citation">
                  {chunk.source_identifier} · chars {chunk.start_char_offset}–{chunk.end_char_offset}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
};
