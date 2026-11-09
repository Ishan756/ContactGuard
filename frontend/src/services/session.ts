export interface ReviewerAuth {
  reviewerId: string;
  apiKey: string;
}

const STORAGE_KEY = "contractguard.reviewerAuth";
const AUTH_EVENT = "contractguard.authChanged";

function devDefaultAuth(): ReviewerAuth | null {
  if (!import.meta.env.DEV) {
    return null;
  }
  return {
    reviewerId: import.meta.env.VITE_REVIEWER_ID || "local-reviewer",
    apiKey: import.meta.env.VITE_WORKFLOW_API_KEY || "dev-workflow-review-key",
  };
}

export function getReviewerAuth(): ReviewerAuth | null {
  if (typeof window === "undefined") {
    return devDefaultAuth();
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ReviewerAuth>;
      if (parsed.reviewerId && parsed.apiKey) {
        return { reviewerId: parsed.reviewerId, apiKey: parsed.apiKey };
      }
    }
  } catch {
    // Ignore malformed local state and fall back to development defaults.
  }
  return devDefaultAuth();
}

export function saveReviewerAuth(auth: ReviewerAuth | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (auth && auth.reviewerId.trim() && auth.apiKey.trim()) {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        reviewerId: auth.reviewerId.trim(),
        apiKey: auth.apiKey.trim(),
      })
    );
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
  window.dispatchEvent(new CustomEvent(AUTH_EVENT));
}

export function subscribeReviewerAuth(listener: () => void): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }
  const handler = () => listener();
  window.addEventListener(AUTH_EVENT, handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener(AUTH_EVENT, handler);
    window.removeEventListener("storage", handler);
  };
}

export function hasReviewerAuth(): boolean {
  return getReviewerAuth() !== null;
}
