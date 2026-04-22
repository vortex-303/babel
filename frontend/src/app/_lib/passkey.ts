"use client";

import {
  startAuthentication,
  startRegistration,
} from "@simplewebauthn/browser";

// Key in localStorage where we stash the babel-minted JWT after a successful
// passkey ceremony. The api() wrapper prefers this over the Supabase token
// so passkey users don't need a Supabase session.
const BABEL_TOKEN_KEY = "babel:passkey-token";
const BABEL_EMAIL_KEY = "babel:passkey-email";

export function getPasskeyToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(BABEL_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getPasskeyEmail(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(BABEL_EMAIL_KEY);
  } catch {
    return null;
  }
}

function persist(token: string, email: string | null) {
  try {
    window.localStorage.setItem(BABEL_TOKEN_KEY, token);
    if (email) window.localStorage.setItem(BABEL_EMAIL_KEY, email);
    else window.localStorage.removeItem(BABEL_EMAIL_KEY);
  } catch {
    /* ignore */
  }
}

export function clearPasskey(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(BABEL_TOKEN_KEY);
    window.localStorage.removeItem(BABEL_EMAIL_KEY);
  } catch {
    /* ignore */
  }
}

export async function registerPasskey(email: string): Promise<{ email: string }> {
  const beginRes = await fetch("/api/passkey/register/begin", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!beginRes.ok) throw new Error(await friendlyError(beginRes));
  const { challenge_id, options } = await beginRes.json();

  const credential = await startRegistration(options);

  const completeRes = await fetch("/api/passkey/register/complete", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ challenge_id, credential, label: email }),
  });
  if (!completeRes.ok) throw new Error(await friendlyError(completeRes));
  const { access_token, email: serverEmail } = await completeRes.json();
  persist(access_token, serverEmail ?? email);
  return { email: serverEmail ?? email };
}

export async function signInWithPasskey(): Promise<{ email: string | null }> {
  const beginRes = await fetch("/api/passkey/login/begin", { method: "POST" });
  if (!beginRes.ok) throw new Error(await friendlyError(beginRes));
  const { challenge_id, options } = await beginRes.json();

  const credential = await startAuthentication(options);

  const completeRes = await fetch("/api/passkey/login/complete", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ challenge_id, credential }),
  });
  if (!completeRes.ok) throw new Error(await friendlyError(completeRes));
  const { access_token, email } = await completeRes.json();
  persist(access_token, email);
  return { email: email ?? null };
}

async function friendlyError(r: Response): Promise<string> {
  try {
    const j = await r.json();
    return typeof j.detail === "string" ? j.detail : r.statusText;
  } catch {
    return r.statusText;
  }
}
