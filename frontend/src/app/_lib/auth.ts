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

export type AuthState = {
  signedIn: boolean;
  displayEmail: string | null;
};

/** Tracks Supabase auth state + the backend profile (credits). */
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

  const refreshProfile = async () => {
    if (!session) {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const auth: AuthState = session
    ? {
        signedIn: true,
        displayEmail: profile?.email ?? session.user.email ?? null,
      }
    : { signedIn: false, displayEmail: null };

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
  const sb = getSupabase();
  if (sb) await sb.auth.signOut();
}
