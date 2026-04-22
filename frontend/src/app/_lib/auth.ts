"use client";

import { useEffect, useState } from "react";

import { api } from "./admin";
import {
  clearPasskey,
  getPasskeyEmail,
  getPasskeyToken,
} from "./passkey";
import { getSessionId } from "./session";
import { getSupabase, type Session } from "./supabase";

export type Profile = {
  user_id: string;
  email: string | null;
  credits_balance: number;
  credits_used: number;
};

export type AuthState = {
  /** True when either Supabase session OR a passkey token is present. */
  signedIn: boolean;
  /** "passkey" | "supabase" | null — null before load, useful for UI. */
  provider: "passkey" | "supabase" | null;
  /** Human-readable identifier for the pill. */
  displayEmail: string | null;
};

/** Tracks auth state across both Supabase and babel-passkey providers. */
export function useAuth(): {
  session: Session | null;
  profile: Profile | null;
  loading: boolean;
  auth: AuthState;
  refreshProfile: () => Promise<void>;
} {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [passkeyEmail, setPasskeyEmail] = useState<string | null>(null);

  const refreshProfile = async () => {
    // Either a passkey token or a Supabase session can drive the profile
    // fetch — api() picks whichever is present as the Authorization header.
    const hasAny = !!getPasskeyToken() || !!session;
    if (!hasAny) {
      setProfile(null);
      return;
    }
    try {
      const res = await api("/api/billing/me");
      if (res.ok) setProfile((await res.json()) as Profile);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    let mounted = true;
    const sb = getSupabase();

    void (async () => {
      setPasskeyEmail(getPasskeyEmail());

      if (sb) {
        const {
          data: { session: s },
        } = await sb.auth.getSession();
        if (mounted) setSession(s);
        if (s) {
          const gid = getSessionId();
          if (gid && gid !== s.user.id) {
            try {
              await api("/api/documents/claim", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ session_id: gid }),
              });
            } catch {
              /* ignore */
            }
          }
        }
      }

      if (mounted) {
        await refreshProfile();
        setLoading(false);
      }
    })();

    let unsub: (() => void) | null = null;
    if (sb) {
      const { data: sub } = sb.auth.onAuthStateChange(
        (_event: string, s: Session | null) => {
          if (!mounted) return;
          setSession(s);
          void refreshProfile();
        },
      );
      unsub = () => sub.subscription.unsubscribe();
    }

    // Passkey token changes via localStorage events (other tabs) OR our own
    // sign-in/out calls. Listen to storage + window focus so the pill stays
    // accurate without a reload.
    const onStorage = () => {
      setPasskeyEmail(getPasskeyEmail());
      void refreshProfile();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", onStorage);

    return () => {
      mounted = false;
      unsub?.();
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onStorage);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const auth: AuthState = (() => {
    const hasPasskey = !!getPasskeyToken();
    if (hasPasskey) {
      return {
        signedIn: true,
        provider: "passkey",
        displayEmail: passkeyEmail ?? profile?.email ?? null,
      };
    }
    if (session) {
      return {
        signedIn: true,
        provider: "supabase",
        displayEmail: profile?.email ?? session.user.email ?? null,
      };
    }
    return { signedIn: false, provider: null, displayEmail: null };
  })();

  return { session, profile, loading, auth, refreshProfile };
}

export async function signInWithPassword(
  email: string,
  password: string,
): Promise<{ needsVerification: boolean }> {
  const sb = getSupabase();
  if (!sb) throw new Error("auth not configured");
  const { error } = await sb.auth.signInWithPassword({ email, password });
  if (!error) return { needsVerification: false };
  // Supabase returns a specific code when the user exists but hasn't clicked
  // their verification link yet. Surface that to the UI so it can prompt a
  // resend rather than showing "bad credentials".
  const msg = (error.message ?? "").toLowerCase();
  if (
    error.code === "email_not_confirmed" ||
    msg.includes("email not confirmed") ||
    msg.includes("not been confirmed")
  ) {
    return { needsVerification: true };
  }
  throw error;
}

export async function signUpWithPassword(
  email: string,
  password: string,
): Promise<{ signedIn: boolean }> {
  const sb = getSupabase();
  if (!sb) throw new Error("auth not configured");
  const redirectTo =
    typeof window !== "undefined" ? `${window.location.origin}/app` : undefined;
  const { data, error } = await sb.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: redirectTo },
  });
  if (error) throw error;
  // When Supabase's "Confirm email" is OFF, signUp returns a real session and
  // the user is immediately signed in. When it's ON, session is null and the
  // user needs to click the email link first.
  return { signedIn: !!data.session };
}

export async function resendVerification(email: string): Promise<void> {
  const sb = getSupabase();
  if (!sb) throw new Error("auth not configured");
  const redirectTo =
    typeof window !== "undefined" ? `${window.location.origin}/app` : undefined;
  const { error } = await sb.auth.resend({
    type: "signup",
    email,
    options: { emailRedirectTo: redirectTo },
  });
  if (error) throw error;
}

export async function signOut(): Promise<void> {
  clearPasskey();
  const sb = getSupabase();
  if (sb) await sb.auth.signOut();
}
