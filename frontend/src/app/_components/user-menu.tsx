"use client";

import { useEffect, useState } from "react";

import { api, getAdminCode, setAdminCode } from "@/app/_lib/admin";

export function UserMenu() {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    setCode(getAdminCode());
  }, []);

  const isAdmin = !!code;

  const signIn = async () => {
    setError(null);
    setChecking(true);
    try {
      // Verify against backend before persisting — better UX than silently
      // storing a wrong code.
      const res = await fetch("/api/admin/whoami", {
        headers: { "X-Admin-Code": draft },
      });
      if (!res.ok) {
        throw new Error("code rejected");
      }
      setAdminCode(draft);
      setCode(draft);
      setDraft("");
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "sign-in failed");
    } finally {
      setChecking(false);
    }
  };

  const signOut = () => {
    setAdminCode(null);
    setCode(null);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-2 ${
          isAdmin
            ? "bg-emerald-600/10 text-emerald-700 dark:text-emerald-300 border border-emerald-600/30"
            : "border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300"
        }`}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            isAdmin ? "bg-emerald-500" : "bg-zinc-400"
          }`}
        />
        {isAdmin ? "Admin" : "Guest"}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 shadow-lg p-3 z-30 text-sm">
          {isAdmin ? (
            <>
              <p className="text-xs text-zinc-500 mb-2">
                Signed in as <span className="font-medium">admin</span>
              </p>
              <a
                href="/admin"
                className="block w-full text-center py-1.5 mb-1 rounded-md border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                Admin panel
              </a>
              <button
                type="button"
                onClick={signOut}
                className="block w-full text-center py-1.5 rounded-md text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <p className="text-xs text-zinc-500 mb-2">
                Enter admin pass-code to unlock full access.
              </p>
              <input
                type="password"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void signIn();
                }}
                placeholder="pass-code"
                className="w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-1.5 mb-2 text-sm"
              />
              {error && (
                <p className="text-xs text-red-600 dark:text-red-400 mb-2">
                  {error}
                </p>
              )}
              <button
                type="button"
                disabled={checking || !draft}
                onClick={() => void signIn()}
                className="w-full py-1.5 rounded-md bg-zinc-900 text-white text-xs font-medium disabled:opacity-50 dark:bg-white dark:text-black"
              >
                {checking ? "Checking…" : "Sign in"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// Keep the type-only re-export helpful for downstream code.
export { api };
