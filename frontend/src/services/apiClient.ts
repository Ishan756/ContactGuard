import type {
  APIErrorResponse,
  LiveHealthResponse,
  ReadyHealthResponse,
  RootHealthResponse,
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

export class ContractGuardApiClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    // In Vite dev mode, default to "" so requests hit Vite dev proxy (/api & /health)
    this.baseUrl = baseUrl !== undefined ? baseUrl : (import.meta.env.VITE_API_BASE_URL || "");
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const requestId = crypto.randomUUID ? crypto.randomUUID() : `fe-${Date.now()}`;

    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (!headers.has("X-Request-ID")) {
      headers.set("X-Request-ID", requestId);
    }
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
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
          // Response body was not JSON
        }

        const message = errorData?.error?.message || `Request failed with status ${response.status}`;
        const code = errorData?.error?.code || `HTTP_${response.status}`;
        const details = errorData?.error?.details;

        throw new ApiClientError(
          message,
          response.status,
          code,
          details,
          responseRequestId
        );
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
}

export const apiClient = new ContractGuardApiClient();
