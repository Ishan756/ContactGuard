export type HealthStatus = "healthy" | "degraded" | "unhealthy";
export type DocumentStatus = "pending" | "processing" | "completed" | "failed" | "needs_ocr";

export interface ComponentHealth {
  status: HealthStatus;
  details?: string;
  latency_ms?: number;
}

export interface RootHealthResponse {
  status: string;
  service: string;
  version: string;
  docs_url: string;
  timestamp: string;
}

export interface LiveHealthResponse {
  status: string;
  timestamp: string;
  uptime_seconds: number;
}

export interface ReadyHealthResponse {
  status: HealthStatus;
  app: string;
  version: string;
  environment: string;
  timestamp: string;
  components: Record<string, ComponentHealth>;
}

export interface APIErrorDetail {
  code: string;
  message: string;
  details?: unknown;
}

export interface APIErrorResponse {
  error: APIErrorDetail;
  request_id?: string;
  timestamp: string;
}

export interface ApiResponseWrapper<T> {
  success: boolean;
  data: T;
  request_id?: string;
  timestamp: string;
}

export interface DocumentChunkResponse {
  id: string;
  document_id: string;
  page_number: number;
  section_heading?: string | null;
  chunk_index: number;
  text: string;
  start_char_offset: number;
  end_char_offset: number;
  source_identifier: string;
}

export interface DocumentMetadataResponse {
  id: string;
  original_filename: string;
  file_size_bytes: number;
  mime_type: string;
  file_hash_sha256: string;
  status: DocumentStatus;
  error_message?: string | null;
  total_pages: number;
  total_characters: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse {
  document: DocumentMetadataResponse;
  chunks_extracted: number;
  message: string;
}

export interface DocumentTextResponse {
  document_id: string;
  total_chunks: number;
  page: number;
  page_size: number;
  has_more: boolean;
  chunks: DocumentChunkResponse[];
}

export interface DocumentListResponse {
  documents: DocumentMetadataResponse[];
  total: number;
}
