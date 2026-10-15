export type HealthStatus = "healthy" | "degraded" | "unhealthy";

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
