// Admin pass-code is kept in localStorage client-side. The backend accepts it
// via the X-Admin-Code header — same value for every admin-gated call. Clears
// gracefully if the user's browser doesn't have localStorage (SSR, Safari
// private mode under some configs).

export const ADMIN_CODE_KEY = "babel:admin-code";

export function getAdminCode(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ADMIN_CODE_KEY);
  } catch {
    return null;
  }
}

export function setAdminCode(code: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (code) window.localStorage.setItem(ADMIN_CODE_KEY, code);
    else window.localStorage.removeItem(ADMIN_CODE_KEY);
  } catch {
    /* ignore */
  }
}

export function adminHeaders(): Record<string, string> {
  const code = getAdminCode();
  return code ? { "X-Admin-Code": code } : {};
}

/** Thin wrapper over fetch that attaches the admin header when present. */
export async function api(input: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  for (const [k, v] of Object.entries(adminHeaders())) headers.set(k, v);
  return fetch(input, { ...init, headers });
}
