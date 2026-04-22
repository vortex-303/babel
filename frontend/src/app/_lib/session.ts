// Anonymous session identity for Phase D0 tenancy. One UUID per browser,
// persisted in localStorage. Attached as X-Session-ID on every backend
// call so the server can filter documents + jobs per-owner.

const SESSION_KEY = "babel:session-id";

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for old browsers (unlikely for our target) — 32 hex chars.
  return Array.from({ length: 32 }, () =>
    Math.floor(Math.random() * 16).toString(16),
  ).join("");
}

export function getSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    let id = window.localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = newId();
      window.localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    // Private browsing modes or storage disabled — fall back to a per-page
    // random id. Worse UX (files scoped to this tab only) but not broken.
    return newId();
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}
