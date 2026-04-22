"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getAdminCode, setAdminCode } from "@/app/_lib/admin";
import { signInWithEmail, signOut, useAuth } from "@/app/_lib/auth";
import { isAuthConfigured } from "@/app/_lib/supabase";

type Mode = "menu" | "signin" | "admin";

export function UserMenu() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("menu");
  const [code, setCode] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { session, profile } = useAuth();
  const signedIn = !!session;
  const isAdmin = !!code;
  const authAvailable = isAuthConfigured();

  useEffect(() => {
    setCode(getAdminCode());
  }, []);

  const submitMagicLink = async () => {
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      await signInWithEmail(email.trim());
      setMessage("Check your email for the sign-in link.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  const signInAdmin = async () => {
    setError(null);
    setBusy(true);
    try {
      const res = await fetch("/api/admin/whoami", {
        headers: { "X-Admin-Code": draft },
      });
      if (!res.ok) throw new Error("code rejected");
      setAdminCode(draft);
      setCode(draft);
      setDraft("");
      setOpen(false);
      setMode("menu");
    } catch (e) {
      setError(e instanceof Error ? e.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  const signOutAll = async () => {
    if (signedIn) await signOut();
    setAdminCode(null);
    setCode(null);
    setOpen(false);
    setMode("menu");
  };

  const pillLabel = isAdmin
    ? "Admin"
    : signedIn
      ? (profile?.email ?? session?.user?.email ?? "Signed in")
      : "Sign in";
  const pillTone = isAdmin
    ? "bg-emerald-600/10 text-emerald-700 dark:text-emerald-300 border-emerald-600/30"
    : signedIn
      ? "bg-blue-600/10 text-blue-700 dark:text-blue-300 border-blue-600/30"
      : "text-zinc-600 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          setMode("menu");
          setError(null);
          setMessage(null);
        }}
        className={`px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-2 border ${pillTone}`}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            isAdmin ? "bg-emerald-500" : signedIn ? "bg-blue-500" : "bg-zinc-400"
          }`}
        />
        <span className="max-w-[160px] truncate">{pillLabel}</span>
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-72 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 shadow-lg p-3 z-30 text-sm">
          {mode === "menu" && (
            <>
              {signedIn && profile && (
                <div className="mb-3 px-2 py-2 rounded-md bg-zinc-50 dark:bg-zinc-900">
                  <p className="text-xs text-zinc-500 truncate">{profile.email}</p>
                  <p className="font-medium">
                    {profile.credits_balance.toLocaleString()} words
                  </p>
                  <Link
                    href="/app/billing"
                    onClick={() => setOpen(false)}
                    className="text-xs text-emerald-700 dark:text-emerald-400 hover:underline"
                  >
                    Buy more →
                  </Link>
                </div>
              )}
              {!signedIn && authAvailable && (
                <button
                  type="button"
                  onClick={() => {
                    setMode("signin");
                    setError(null);
                    setMessage(null);
                  }}
                  className="block w-full text-left py-1.5 px-2 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-900"
                >
                  Sign in / sign up
                </button>
              )}
              {!isAdmin && (
                <button
                  type="button"
                  onClick={() => {
                    setMode("admin");
                    setError(null);
                  }}
                  className="block w-full text-left py-1.5 px-2 rounded-md text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
                >
                  Admin pass-code
                </button>
              )}
              {isAdmin && (
                <Link
                  href="/admin"
                  onClick={() => setOpen(false)}
                  className="block w-full text-center py-1.5 mb-1 rounded-md border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-900"
                >
                  Admin panel
                </Link>
              )}
              {(signedIn || isAdmin) && (
                <button
                  type="button"
                  onClick={signOutAll}
                  className="block w-full text-center py-1.5 rounded-md text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40"
                >
                  Sign out
                </button>
              )}
            </>
          )}

          {mode === "signin" && (
            <>
              <p className="text-xs text-zinc-500 mb-2">
                We’ll email you a one-time sign-in link.
              </p>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void submitMagicLink();
                }}
                placeholder="you@example.com"
                className="w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-1.5 mb-2 text-sm"
              />
              {error && (
                <p className="text-xs text-red-600 dark:text-red-400 mb-2">{error}</p>
              )}
              {message && (
                <p className="text-xs text-emerald-700 dark:text-emerald-400 mb-2">
                  {message}
                </p>
              )}
              <button
                type="button"
                disabled={busy || !email}
                onClick={() => void submitMagicLink()}
                className="w-full py-1.5 rounded-md bg-zinc-900 text-white text-xs font-medium disabled:opacity-50 dark:bg-white dark:text-black"
              >
                {busy ? "Sending…" : "Send magic link"}
              </button>
              <button
                type="button"
                onClick={() => setMode("menu")}
                className="w-full mt-1 py-1 rounded-md text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                Cancel
              </button>
            </>
          )}

          {mode === "admin" && (
            <>
              <p className="text-xs text-zinc-500 mb-2">
                Admin pass-code unlocks the operator panel.
              </p>
              <input
                type="password"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void signInAdmin();
                }}
                placeholder="pass-code"
                className="w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-1.5 mb-2 text-sm"
              />
              {error && (
                <p className="text-xs text-red-600 dark:text-red-400 mb-2">{error}</p>
              )}
              <button
                type="button"
                disabled={busy || !draft}
                onClick={() => void signInAdmin()}
                className="w-full py-1.5 rounded-md bg-zinc-900 text-white text-xs font-medium disabled:opacity-50 dark:bg-white dark:text-black"
              >
                {busy ? "Checking…" : "Unlock admin"}
              </button>
              <button
                type="button"
                onClick={() => setMode("menu")}
                className="w-full mt-1 py-1 rounded-md text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                Cancel
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export { api };
