import React, { useState, useEffect } from "react";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { BookOpen, Search, Plus, AlertCircle, CheckCircle, RefreshCw } from "lucide-react";

interface Policy {
  id: string;
  name: string;
  version: string;
  category: string | null;
  description: string | null;
  status: string;
  total_chunks: number;
  created_at: string;
}

interface SearchResult {
  chunk_id: string;
  policy_id: string;
  policy_name: string;
  policy_version: string;
  category: string | null;
  section_heading: string | null;
  page_number: number;
  text: string;
  similarity_score: number;
  retrieval_disclaimer: string;
}

export const PoliciesPage: React.FC = () => {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form states for creating policy
  const [newPolicyName, setNewPolicyName] = useState("");
  const [newPolicyVersion, setNewPolicyVersion] = useState("1.0.0");
  const [newPolicyCategory, setNewPolicyCategory] = useState("Liability");
  const [newPolicyText, setNewPolicyText] = useState("");
  const [creating, setCreating] = useState(false);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchCategory, setSearchCategory] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);

  const fetchPolicies = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/api/v1/policies");
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      setPolicies(data.items || []);
    } catch (err: any) {
      setError(err.message || "Failed to load policies");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, []);

  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPolicyName.trim() || !newPolicyText.trim()) return;

    setCreating(true);
    setCreateSuccess(null);
    setError(null);

    try {
      const res = await fetch("http://localhost:8000/api/v1/policies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newPolicyName.trim(),
          version: newPolicyVersion.trim(),
          category: newPolicyCategory.trim() || null,
          text_content: newPolicyText.trim(),
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to create policy (${res.status})`);
      }

      setCreateSuccess(`Policy "${newPolicyName}" successfully indexed.`);
      setNewPolicyName("");
      setNewPolicyText("");
      fetchPolicies();
    } catch (err: any) {
      setError(err.message || "Failed to create policy");
    } finally {
      setCreating(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setSearching(true);
    setError(null);

    try {
      const res = await fetch("http://localhost:8000/api/v1/policies/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clause_text: searchQuery.trim(),
          category: searchCategory.trim() || null,
          limit: 5,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Search failed (${res.status})`);
      }

      const data = await res.json();
      setSearchResults(data.matches || []);
    } catch (err: any) {
      setError(err.message || "Search query failed");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div id="policies-page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Company Policy Knowledge Base</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            Upload, index, and retrieve enterprise policies for automated contract clause risk validation.
          </p>
        </div>
        <button
          className="btn btn-secondary"
          onClick={fetchPolicies}
          style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          Refresh
        </button>
      </div>

      {error && (
        <div style={{ backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--accent-rose)", padding: "0.85rem 1.25rem", borderRadius: "8px", marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: "0.75rem", color: "var(--accent-rose)" }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {createSuccess && (
        <div style={{ backgroundColor: "rgba(16, 185, 129, 0.1)", border: "1px solid var(--accent-emerald)", padding: "0.85rem 1.25rem", borderRadius: "8px", marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: "0.75rem", color: "var(--accent-emerald)" }}>
          <CheckCircle size={18} />
          <span>{createSuccess}</span>
        </div>
      )}

      {/* Semantic Clause Retrieval Tester */}
      <Card
        id="card-clause-retrieval"
        title="Semantic Policy Retrieval Tester"
        subtitle="Retrieve relevant policy passages and citations for a sample contract clause"
        style={{ marginBottom: "1.5rem" }}
      >
        <form onSubmit={handleSearch} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.35rem", color: "var(--text-secondary)" }}>
              Contract Clause to Retrieve Against
            </label>
            <textarea
              id="clause-search-input"
              rows={3}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="e.g. Under no circumstances shall either party be liable for indirect or consequential damages, and liability is capped at $50,000."
              style={{
                width: "100%",
                padding: "0.75rem",
                borderRadius: "6px",
                backgroundColor: "var(--bg-subtle)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-primary)",
                fontFamily: "inherit",
                fontSize: "0.9rem",
              }}
            />
          </div>

          <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
            <input
              type="text"
              placeholder="Filter by Category (optional, e.g. Liability)"
              value={searchCategory}
              onChange={(e) => setSearchCategory(e.target.value)}
              style={{
                padding: "0.5rem 0.75rem",
                borderRadius: "6px",
                backgroundColor: "var(--bg-subtle)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-primary)",
                fontSize: "0.85rem",
                flex: 1,
              }}
            />
            <button
              id="btn-search-clause"
              type="submit"
              disabled={searching || !searchQuery.trim()}
              className="btn btn-primary"
              style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
            >
              <Search size={16} />
              {searching ? "Searching..." : "Retrieve Matching Policies"}
            </button>
          </div>
        </form>

        {searchResults.length > 0 && (
          <div style={{ marginTop: "1.5rem" }}>
            <h4 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem", color: "var(--text-primary)" }}>
              Retrieved Passages ({searchResults.length})
            </h4>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {searchResults.map((res) => (
                <div
                  key={res.chunk_id}
                  style={{
                    padding: "1rem",
                    backgroundColor: "var(--bg-subtle)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "8px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontWeight: 600, color: "var(--accent-cyan)" }}>{res.policy_name}</span>
                      <Badge status="neutral">v{res.policy_version}</Badge>
                      {res.category && <Badge status="info">{res.category}</Badge>}
                      {res.section_heading && (
                        <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                          • {res.section_heading}
                        </span>
                      )}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Similarity:</span>
                      <span style={{ fontWeight: 700, color: "var(--accent-emerald)" }}>
                        {(res.similarity_score * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <p style={{ fontSize: "0.875rem", lineHeight: 1.5, color: "var(--text-secondary)", margin: 0 }}>
                    "{res.text}"
                  </p>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem", fontStyle: "italic" }}>
                    {res.retrieval_disclaimer}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <div className="grid-cols-2">
        {/* Existing Policies List */}
        <Card id="card-policies-list" title="Indexed Policies" subtitle={`${policies.length} standard policies loaded`}>
          {loading ? (
            <div style={{ padding: "1rem", textAlign: "center", color: "var(--text-muted)" }}>Loading policies...</div>
          ) : policies.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
              <BookOpen size={32} style={{ margin: "0 auto 0.75rem", opacity: 0.4 }} />
              <div>No company policies indexed yet.</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {policies.map((pol) => (
                <div
                  key={pol.id}
                  style={{
                    padding: "0.75rem",
                    backgroundColor: "var(--bg-subtle)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "6px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>{pol.name}</div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                      v{pol.version} • {pol.category || "General"} • {pol.total_chunks} chunks indexed
                    </div>
                  </div>
                  <Badge status={pol.status === "active" ? "success" : "neutral"}>{pol.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Quick Add Policy Form */}
        <Card id="card-add-policy" title="Index New Policy" subtitle="Add policy text rules to Qdrant vector index">
          <form onSubmit={handleCreatePolicy} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                Policy Name
              </label>
              <input
                type="text"
                required
                value={newPolicyName}
                onChange={(e) => setNewPolicyName(e.target.value)}
                placeholder="e.g. Standard Vendor Indemnity Rule"
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-subtle)",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-primary)",
                  fontSize: "0.85rem",
                }}
              />
            </div>

            <div style={{ display: "flex", gap: "0.75rem" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                  Version
                </label>
                <input
                  type="text"
                  required
                  value={newPolicyVersion}
                  onChange={(e) => setNewPolicyVersion(e.target.value)}
                  placeholder="1.0.0"
                  style={{
                    width: "100%",
                    padding: "0.5rem 0.75rem",
                    borderRadius: "6px",
                    backgroundColor: "var(--bg-subtle)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.85rem",
                  }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                  Category
                </label>
                <input
                  type="text"
                  value={newPolicyCategory}
                  onChange={(e) => setNewPolicyCategory(e.target.value)}
                  placeholder="Liability"
                  style={{
                    width: "100%",
                    padding: "0.5rem 0.75rem",
                    borderRadius: "6px",
                    backgroundColor: "var(--bg-subtle)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.85rem",
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                Policy Rules Text
              </label>
              <textarea
                required
                rows={4}
                value={newPolicyText}
                onChange={(e) => setNewPolicyText(e.target.value)}
                placeholder="SECTION 1. LIABILITY CAP. All vendor contracts must include an aggregate liability limit of 12 months fees..."
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-subtle)",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-primary)",
                  fontSize: "0.85rem",
                  fontFamily: "inherit",
                }}
              />
            </div>

            <button
              id="btn-create-policy"
              type="submit"
              disabled={creating || !newPolicyName.trim() || !newPolicyText.trim()}
              className="btn btn-primary"
              style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", marginTop: "0.5rem" }}
            >
              <Plus size={16} />
              {creating ? "Vectorizing & Saving..." : "Save and Vectorize Policy"}
            </button>
          </form>
        </Card>
      </div>
    </div>
  );
};
