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

  it("uploads contract file with multipart form data", async () => {
    const mockUploadResponse = {
      document: {
        id: "doc-123",
        original_filename: "nda.pdf",
        file_size_bytes: 1024,
        mime_type: "application/pdf",
        file_hash_sha256: "abc123hash",
        status: "completed",
        total_pages: 1,
        total_characters: 500,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      chunks_extracted: 3,
      message: "Uploaded successfully",
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ "X-Request-ID": "upload-req-1" }),
      json: async () => mockUploadResponse,
    });

    const file = new File(["dummy content"], "nda.pdf", { type: "application/pdf" });
    const result = await client.uploadDocument(file);

    expect(result.document.id).toBe("doc-123");
    expect(result.chunks_extracted).toBe(3);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/documents",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      })
    );
  });

  it("lists documents with limit and offset query params", async () => {
    const mockListResponse = {
      documents: [],
      total: 0,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => mockListResponse,
    });

    const result = await client.listDocuments(10, 0);
    expect(result.total).toBe(0);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/documents?limit=10&offset=0",
      expect.anything()
    );
  });
});
