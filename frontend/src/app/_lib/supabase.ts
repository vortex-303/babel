"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { Session } from "@supabase/supabase-js";

// Browser-only Supabase client. Lazy because NEXT_PUBLIC_* env vars may be
// missing during local dev — we want the rest of the app to keep working
// (everyone is effectively a guest) instead of crashing on import.
let _client: ReturnType<typeof createBrowserClient> | null = null;

export function getSupabase() {
  if (_client) return _client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) return null;
  _client = createBrowserClient(url, anon);
  return _client;
}

export function isAuthConfigured(): boolean {
  return (
    !!process.env.NEXT_PUBLIC_SUPABASE_URL &&
    !!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  );
}

export type { Session };
