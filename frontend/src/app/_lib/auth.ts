"use client";

import { useEffect, useState } from "react";

import { api } from "./admin";
import { getSessionId } from "./session";
import { getSupabase, type Session } from "./supabase";

export type Profile = {
  user_id: string;
  email: string | null;
  credits_balance: number;
  credits_used: number;
};

/** Tracks Supabase auth state + fetches the backend profile (credits). */
export function useAuth(): {
  session: Session | null;
  profile: Profile | null;
  loading: boolean;
  refreshProfile: () => Promise<void>;
} {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshProfile = async () => {
    const sb = getSupabase();
    if (!sb) {
      setProfile(null);
      return;
    }
    const {
      data: { session: s },
    } = await sb.auth.getSession();
    if (!s) {
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
    const sb = getSupabase();
    if (!sb) {
      setLoading(false);
      return;
    }
    let mounted = true;

    void (async () => {
      const {
        data: { session: s },
      } = await sb.auth.getSession();
      if (!mounted) return;
      setSession(s);
      if (s) {
        // Claim any guest docs the anon session created before login.
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
        await refreshProfile();
      }
      setLoading(false);
    })();

    const { data: sub } = sb.auth.onAuthStateChange(
      (_event: string, s: Session | null) => {
        if (!mounted) return;
        setSession(s);
        if (s) void refreshProfile();
        else setProfile(null);
      },
    );

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  return { session, profile, loading, refreshProfile };
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
): Promise<void> {
  const sb = getSupabase();
  if (!sb) throw new Error("auth not configured");
  const redirectTo =
    typeof window !== "undefined" ? `${window.location.origin}/app` : undefined;
  const { error } = await sb.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: redirectTo },
  });
  if (error) throw error;
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
  const sb = getSupabase();
  if (!sb) return;
  await sb.auth.signOut();
}
