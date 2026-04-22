"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getAdminCode, setAdminCode } from "@/app/_lib/admin";
import {
  resendVerification,
  signInWithPassword,
  signOut,
  signUpWithPassword,
  useAuth,
} from "@/app/_lib/auth";
import { registerPasskey, signInWithPasskey } from "@/app/_lib/passkey";
import { isAuthConfigured } from "@/app/_lib/supabase";

type Mode = "menu" | "signin" | "signup" | "admin";

export function UserMenu() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("menu");
  const [code, setCode] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [needsVerify, setNeedsVerify] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { profile, auth, refreshProfile } = useAuth();
  const signedIn = auth.signedIn;
  const isAdmin = !!code;
  const authAvailable = isAuthConfigured();

  useEffect(() => {
    setCode(getAdminCode());
  }, []);

  const resetAuthForm = () => {
    setEmail("");
    setPassword("");
    setError(null);
    setMessage(null);
    setNeedsVerify(false);
  };

  const submitSignIn = async () => {
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      const { needsVerification } = await signInWithPassword(
        email.trim(),
        password,
      );
      if (needsVerification) {
        setNeedsVerify(true);
        setMessage(
          "Please verify your email first. Check your inbox for the link.",
        );
        return;
      }
      setOpen(false);
      setMode("menu");
      resetAuthForm();
    } catch (e) {
      setError(friendlyAuthError(e));
    } finally {
      setBusy(false);
    }
  };

  const submitSignUp = async () => {
    setError(null);
    setMessage(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      const { signedIn } = await signUpWithPassword(email.trim(), password);
      if (signedIn) {
        // "Confirm email" is OFF in Supabase — user has a session already.
        setOpen(false);
        setMode("menu");
        resetAuthForm();
      } else {
        setMessage(
          `Verification email sent to ${email}. Click the link, then come back and sign in.`,
        );
        setMode("signin");
        setPassword("");
      }
    } catch (e) {
      setError(friendlyAuthError(e));
    } finally {
      setBusy(false);
    }
  };

  const submitAddPasskey = async () => {
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      await registerPasskey();
      setMessage(
        "Passkey added. You can sign in with Face ID / Touch ID next time.",
      );
      await refreshProfile();
    } catch (e) {
      setError(friendlyAuthError(e));
    } finally {
      setBusy(false);
    }
  };

  const submitPasskeySignIn = async () => {
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      await signInWithPasskey();
      await refreshProfile();
      setOpen(false);
      setMode("menu");
      resetAuthForm();
    } catch (e) {
      setError(friendlyAuthError(e));
    } finally {
      setBusy(false);
    }
  };

  const submitResend = async () => {
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      await resendVerification(email.trim());
      setMessage("Verification email sent. Check your inbox.");
    } catch (e) {
      const msg = friendlyAuthError(e);
      // Rate-limit is the common case here; soften the tone.
      if (msg.toLowerCase().includes("rate")) {
        setError("Too many requests. Wait a minute and try again.");
      } else {
        setError(msg);
      }
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
      ? (auth.displayEmail ?? "Signed in")
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
              {signedIn && (
                <>
                  <button
                    type="button"
                    onClick={() => void submitAddPasskey()}
                    disabled={busy}
                    className="block w-full text-left py-1.5 px-2 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-900 disabled:opacity-50"
                  >
                    <span className="mr-2">🔐</span>
                    {busy ? "Waiting for passkey…" : "Add passkey to this account"}
                  </button>
                  {message && (
                    <p className="text-[11px] text-emerald-700 dark:text-emerald-400 px-2 py-1">
                      {message}
                    </p>
                  )}
                  {error && (
                    <p className="text-[11px] text-red-600 dark:text-red-400 px-2 py-1">
                      {error}
                    </p>
                  )}
                </>
              )}
              {!signedIn && (
                <>
                  <button
                    type="button"
                    onClick={() => void submitPasskeySignIn()}
                    disabled={busy}
                    className="block w-full text-left py-1.5 px-2 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-900 disabled:opacity-50"
                  >
                    <span className="mr-2">🔑</span>Sign in with passkey
                  </button>
                  {busy && !error && (
                    <p className="text-[11px] text-zinc-500 px-2 py-1">
                      Waiting for passkey…
                    </p>
                  )}
                  {error && (
                    <p className="text-[11px] text-red-600 dark:text-red-400 px-2 py-1">
                      {error}
                    </p>
                  )}
                  {authAvailable && (
                    <>
                      <div className="my-1 border-t border-zinc-200 dark:border-zinc-800" />
                      <button
                        type="button"
                        onClick={() => {
                          setMode("signin");
                          resetAuthForm();
                        }}
                        className="block w-full text-left py-1.5 px-2 rounded-md text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
                      >
                        Sign in with email + password
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setMode("signup");
                          resetAuthForm();
                        }}
                        className="block w-full text-left py-1.5 px-2 rounded-md text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
                      >
                        Create email account
                      </button>
                    </>
                  )}
                </>
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

          {(mode === "signin" || mode === "signup") && (
            <form
              method="post"
              action="#"
              onSubmit={(e) => {
                e.preventDefault();
                if (mode === "signin") void submitSignIn();
                else void submitSignUp();
              }}
            >
              <p className="text-xs text-zinc-500 mb-2">
                {mode === "signin"
                  ? "Sign in with your email and password."
                  : "Create an account — we’ll email you a verification link."}
              </p>
              <input
                type="email"
                name="email"
                value={email}
                autoComplete="email"
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-1.5 mb-2 text-sm"
              />
              <input
                type="password"
                name="password"
                value={password}
                autoComplete={
                  mode === "signin" ? "current-password" : "new-password"
                }
                onChange={(e) => setPassword(e.target.value)}
                placeholder={
                  mode === "signin"
                    ? "password"
                    : "password (8+ characters)"
                }
                required
                minLength={mode === "signup" ? 8 : undefined}
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
              {needsVerify && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void submitResend()}
                  className="w-full mb-2 py-1.5 rounded-md border border-emerald-600 text-emerald-700 dark:text-emerald-300 text-xs font-medium disabled:opacity-50"
                >
                  Resend verification email
                </button>
              )}
              <button
                type="submit"
                disabled={busy || !email || !password}
                className="w-full py-1.5 rounded-md bg-zinc-900 text-white text-xs font-medium disabled:opacity-50 dark:bg-white dark:text-black"
              >
                {busy
                  ? mode === "signin"
                    ? "Signing in…"
                    : "Creating…"
                  : mode === "signin"
                    ? "Sign in"
                    : "Create account"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode(mode === "signin" ? "signup" : "signin");
                  resetAuthForm();
                }}
                className="w-full mt-1 py-1 rounded-md text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                {mode === "signin"
                  ? "No account yet? Create one"
                  : "Have an account? Sign in"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("menu");
                  resetAuthForm();
                }}
                className="w-full py-1 rounded-md text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                Cancel
              </button>
            </form>
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

function friendlyAuthError(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const msg = raw.toLowerCase();
  if (msg.includes("invalid login credentials")) return "Wrong email or password.";
  if (msg.includes("user already registered"))
    return "An account with this email already exists. Sign in instead.";
  if (msg.includes("password") && msg.includes("weak"))
    return "Password too weak. Try 8+ characters with mixed types.";
  if (msg.includes("rate")) return "Too many requests. Wait a minute and try again.";
  return raw;
}
