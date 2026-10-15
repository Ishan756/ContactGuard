import { describe, it, expect, vi, beforeEach } from "vitest";
import { ContractGuardApiClient, ApiClientError } from "../services/apiClient";

describe("ContractGuardApiClient", () => {
  let client: ContractGuardApiClient;

  beforeEach(() => {
    client = new ContractGuardApiClient("http://localhost:8000");
    vi.restoreAllMocks();
  });

  it("fetches root health successfully with request id", async () => {
    const mockResponse = {
      status: "ok",
      service: "ContractGuard",
      version: "0.1.0",
      docs_url: "/docs",
      timestamp: new Date().toISOString(),
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ "X-Request-ID": "test-req-123" }),
      json: async () => mockResponse,
    });

    const result = await client.getRootHealth();
    expect(result.status).toBe("ok");
    expect(result.service).toBe("ContractGuard");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({
        headers: expect.any(Headers),
      })
    );
  });

  it("throws ApiClientError with error payload on 404 or 500 status", async () => {
    const errorPayload = {
      error: {
        code: "NOT_FOUND",
        message: "Resource does not exist",
        details: null,
      },
      request_id: "error-req-999",
      timestamp: new Date().toISOString(),
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers({ "X-Request-ID": "error-req-999" }),
      json: async () => errorPayload,
    });

    await expect(client.getRootHealth()).rejects.toThrow(ApiClientError);

    try {
      await client.getRootHealth();
    } catch (err: unknown) {
      const apiErr = err as ApiClientError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.code).toBe("NOT_FOUND");
      expect(apiErr.message).toBe("Resource does not exist");
      expect(apiErr.requestId).toBe("error-req-999");
    }
  });
});
