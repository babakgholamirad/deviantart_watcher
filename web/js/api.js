/*
Module: api.js

Variables and behavior:
- Encapsulates HTTP calls used by the UI (`defaults`, `gallery`, `job status`, and JSON POST/PATCH routes).

How this module works:
- Returns parsed JSON responses where possible, while preserving HTTP status checks
  so the caller controls success/error messaging.
*/

async function parseJsonSafe(response) {
  try {
    return await response.json();
  } catch (_error) {
    return {};
  }
}

export async function postJson(url, payload, method = "POST") {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await parseJsonSafe(response);
  return { response, data };
}

export async function fetchDefaults() {
  const response = await fetch("/api/defaults", { cache: "no-store" });
  if (!response.ok) {
    return null;
  }
  return parseJsonSafe(response);
}

export async function fetchGallery(searchQuery = "", favoritesOnly = false) {
  const params = new URLSearchParams();
  if (searchQuery) {
    params.set("q", searchQuery);
  }
  if (favoritesOnly) {
    params.set("favorites_only", "1");
  }

  const queryString = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`/api/gallery${queryString}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load gallery.");
  }

  return parseJsonSafe(response);
}

export async function fetchJobStatus() {
  const response = await fetch("/api/job/status", { cache: "no-store" });
  if (!response.ok) {
    return null;
  }
  return parseJsonSafe(response);
}
