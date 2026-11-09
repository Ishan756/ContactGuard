import { getReviewerAuth } from "./session";
import type {
  APIErrorResponse,
  ClauseListResponse,
  DocumentListResponse,
  DocumentMetadataResponse,
  DocumentTextResponse,
  DocumentUploadResponse,
  LiveHealthResponse,
  PolicyCreateRequest,
  PolicyListResponse,
  PolicyResponse,
  PolicySearchResponse,
  PolicyUploadMetadata,
  ReadyHealthResponse,
  RiskFindingListResponse,
  RiskFindingResponse,
  RootHealthResponse,
  WorkflowResultsResponse,
  WorkflowResumeRequest,
  WorkflowRunListResponse,
  WorkflowRunResponse,
  WorkflowStartRequest,
} from "../types/api";

export class ApiClientError extends Error {
  public status: number;
  public code: string;
  public details?: unknown;
  public requestId?: string;

  constructor(
    message: string,
    status: number,
    code: string = "API_ERROR",
    details?: unknown,
    requestId?: string
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

type RequestAuth = "none" | "reviewer";

interface RequestOptions extends RequestInit {
  auth?: RequestAuth;
  idempotencyKey?: string;
}

function queryString(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export class ContractGuardApiClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl =
      baseUrl !== undefined ? baseUrl : import.meta.env.VITE_API_BASE_URL || "";
  }

  private applyReviewerAuth(headers: Headers): void {
    const auth = getReviewerAuth();
    if (!auth) {
      throw new ApiClientError(
        "Reviewer credentials are required. Add a reviewer ID and API key in Settings.",
        401,
        "REVIEWER_AUTH_REQUIRED"
      );
    }
    headers.set("X-Reviewer-ID", auth.reviewerId);
    headers.set("X-Workflow-Key", auth.apiKey);
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const requestId = globalThis.crypto?.randomUUID?.() ?? `fe-${Date.now()}`;

    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (!headers.has("X-Request-ID")) {
      headers.set("X-Request-ID", requestId);
    }
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (options.idempotencyKey) {
      headers.set("Idempotency-Key", options.idempotencyKey);
    }
    if (options.auth === "reviewer") {
      this.applyReviewerAuth(headers);
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      const responseRequestId = response.headers.get("X-Request-ID") || requestId;

      if (!response.ok) {
        let errorData: APIErrorResponse | null = null;
        try {
          errorData = await response.json();
        } catch {
          // Response body was not JSON.
        }

        const message =
          errorData?.error?.message || `Request failed with status ${response.status}`;
        const code = errorData?.error?.code || `HTTP_${response.status}`;
        const details = errorData?.error?.details;

        throw new ApiClientError(message, response.status, code, details, responseRequestId);
      }

      if (response.status === 204) {
        return undefined as T;
      }
      return (await response.json()) as T;
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        throw err;
      }
      throw new ApiClientError(
        err instanceof Error ? err.message : "Network request failed",
        0,
        "NETWORK_ERROR"
      );
    }
  }

  public async getRootHealth(): Promise<RootHealthResponse> {
    return this.request<RootHealthResponse>("/health");
  }

  public async getLiveHealth(): Promise<LiveHealthResponse> {
    return this.request<LiveHealthResponse>("/api/v1/health/live");
  }

  public async getReadyHealth(): Promise<ReadyHealthResponse> {
    return this.request<ReadyHealthResponse>("/api/v1/health/ready");
  }

  public async uploadDocument(file: File): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request<DocumentUploadResponse>("/api/v1/documents", {
      method: "POST",
      body: formData,
    });
  }

  public async listDocuments(limit: number = 20, offset: number = 0): Promise<DocumentListResponse> {
    return this.request<DocumentListResponse>(
      `/api/v1/documents${queryString({ limit, offset })}`
    );
  }

  public async getDocument(id: string): Promise<DocumentMetadataResponse> {
    return this.request<DocumentMetadataResponse>(`/api/v1/documents/${id}`);
  }

  public async getDocumentChunks(
    id: string,
    page: number = 1,
    pageSize: number = 20
  ): Promise<DocumentTextResponse> {
    return this.request<DocumentTextResponse>(
      `/api/v1/documents/${id}/chunks${queryString({ page, page_size: pageSize })}`
    );
  }

  public async listClauses(documentId: string, limit: number = 200): Promise<ClauseListResponse> {
    return this.request<ClauseListResponse>(
      `/api/v1/documents/${documentId}/clauses${queryString({ limit })}`
    );
  }

  public async listFindings(
    documentId: string,
    params: {
      analysisRunId?: string;
      severity?: string;
      category?: string;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<RiskFindingListResponse> {
    return this.request<RiskFindingListResponse>(
      `/api/v1/documents/${documentId}/findings${queryString({
        analysis_run_id: params.analysisRunId,
        severity: params.severity,
        category: params.category,
        limit: params.limit ?? 500,
        offset: params.offset ?? 0,
      })}`
    );
  }

  public async getFinding(documentId: string, findingId: string): Promise<RiskFindingResponse> {
    return this.request<RiskFindingResponse>(
      `/api/v1/documents/${documentId}/findings/${findingId}`
    );
  }

  public async listPolicies(
    limit: number = 100,
    offset: number = 0,
    filters: { category?: string; status?: string } = {}
  ): Promise<PolicyListResponse> {
    return this.request<PolicyListResponse>(
      `/api/v1/policies${queryString({
        limit,
        offset,
        category: filters.category,
        status: filters.status,
      })}`
    );
  }

  public async createPolicy(request: PolicyCreateRequest): Promise<PolicyResponse> {
    return this.request<PolicyResponse>("/api/v1/policies", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  public async uploadPolicyDocument(
    metadata: PolicyUploadMetadata,
    file: File
  ): Promise<PolicyResponse> {
    const formData = new FormData();
    formData.append("name", metadata.name);
    formData.append("version", metadata.version || "1.0.0");
    if (metadata.category) {
      formData.append("category", metadata.category);
    }
    if (metadata.description) {
      formData.append("description", metadata.description);
    }
    formData.append("file", file);
    return this.request<PolicyResponse>("/api/v1/policies/upload", {
      method: "POST",
      body: formData,
    });
  }

  public async searchPolicies(
    query: string,
    category?: string,
    limit: number = 8
  ): Promise<PolicySearchResponse> {
    return this.request<PolicySearchResponse>("/api/v1/policies/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        category: category || null,
        limit,
      }),
    });
  }

  public async listWorkflows(
    params: {
      documentId?: string;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<WorkflowRunListResponse> {
    return this.request<WorkflowRunListResponse>(
      `/api/v1/workflows${queryString({
        document_id: params.documentId,
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      })}`,
      { auth: "reviewer" }
    );
  }

  public async startWorkflow(
    request: WorkflowStartRequest,
    idempotencyKey?: string
  ): Promise<WorkflowRunResponse> {
    return this.request<WorkflowRunResponse>("/api/v1/workflows", {
      method: "POST",
      body: JSON.stringify(request),
      auth: "reviewer",
      idempotencyKey,
    });
  }

  public async getWorkflow(workflowId: string): Promise<WorkflowRunResponse> {
    return this.request<WorkflowRunResponse>(`/api/v1/workflows/${workflowId}`, {
      auth: "reviewer",
    });
  }

  public async getWorkflowResults(workflowId: string): Promise<WorkflowResultsResponse> {
    return this.request<WorkflowResultsResponse>(
      `/api/v1/workflows/${workflowId}/results`,
      { auth: "reviewer" }
    );
  }

  public async resumeWorkflow(
    workflowId: string,
    request: WorkflowResumeRequest,
    idempotencyKey?: string
  ): Promise<WorkflowRunResponse> {
    return this.request<WorkflowRunResponse>(`/api/v1/workflows/${workflowId}/resume`, {
      method: "POST",
      body: JSON.stringify(request),
      auth: "reviewer",
      idempotencyKey: idempotencyKey || request.command_id,
    });
  }
}

export const apiClient = new ContractGuardApiClient();
