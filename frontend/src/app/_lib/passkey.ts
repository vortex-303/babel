"use client";

import {
  startAuthentication,
  startRegistration,
} from "@simplewebauthn/browser";

import { api } from "./admin";
import { getSupabase } from "./supabase";

/**
 * Register a new passkey on the currently-signed-in Supabase account.
 * Browser prompts for Face ID / Touch ID / Windows Hello; on success the
 * credential is stored against `auth.users.id` on the backend.
 */
export async function registerPasskey(): Promise<void> {
  const beginRes = await api("/api/passkey/register/begin", { method: "POST" });
  if (!beginRes.ok) throw new Error(await friendlyError(beginRes));
  const { challenge_id, options } = await beginRes.json();

  const credential = await startRegistration({ optionsJSON: options });

  const completeRes = await api("/api/passkey/register/complete", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ challenge_id, credential }),
  });
  if (!completeRes.ok) throw new Error(await friendlyError(completeRes));
}

/**
 * Sign in using a previously registered passkey. After WebAuthn verifies
 * the assertion, the backend returns a Supabase magic-link token_hash;
 * we hand that to supabase.auth.verifyOtp to install a real Supabase
 * session. No email is ever sent.
 */
export async function signInWithPasskey(): Promise<{ email: string }> {
  const sb = getSupabase();
  if (!sb) throw new Error("Supabase not configured on this deployment.");

  const beginRes = await fetch("/api/passkey/login/begin", { method: "POST" });
  if (!beginRes.ok) throw new Error(await friendlyError(beginRes));
  const { challenge_id, options } = await beginRes.json();

  const credential = await startAuthentication({ optionsJSON: options });

  const completeRes = await fetch("/api/passkey/login/complete", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ challenge_id, credential }),
  });
  if (!completeRes.ok) throw new Error(await friendlyError(completeRes));
  const { email, token_hash } = await completeRes.json();

  const { error } = await sb.auth.verifyOtp({
    token_hash,
    type: "magiclink",
  });
  if (error) throw error;

  return { email };
}

export type PasskeyCredentialInfo = {
  credential_id: string;
  label: string | null;
  created_at: string;
  last_used_at: string | null;
};

export async function listPasskeys(): Promise<PasskeyCredentialInfo[]> {
  const r = await api("/api/passkey/credentials");
  if (!r.ok) throw new Error(await friendlyError(r));
  const { credentials } = (await r.json()) as {
    credentials: PasskeyCredentialInfo[];
  };
  return credentials;
}

export async function deletePasskey(credentialId: string): Promise<void> {
  const r = await api(
    `/api/passkey/credentials/${encodeURIComponent(credentialId)}`,
    { method: "DELETE" },
  );
  if (!r.ok) throw new Error(await friendlyError(r));
}

async function friendlyError(r: Response): Promise<string> {
  try {
    const j = await r.json();
    return typeof j.detail === "string" ? j.detail : r.statusText;
  } catch {
    return r.statusText;
  }
}
