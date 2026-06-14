"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { LogoIcon } from "@/components/icons";

export default function LoginPage() {
  const { user, loading, login, register } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/chat");
  }, [loading, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name || undefined);
      router.replace("/chat");
    } catch (err) {
      setError(humanize(String(err)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="card w-full max-w-sm p-7 shadow-lg">
        <div className="mb-5">
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/30 bg-accent/10">
              <LogoIcon className="h-5 w-5 text-accent" />
            </span>
            <span className="text-lg font-semibold tracking-tight">AgentStack</span>
          </div>
          <h1 className="text-base font-semibold">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            {mode === "login"
              ? "Sign in to your account to continue."
              : "Get started with your own RAG workspace."}
          </p>
        </div>

        <form onSubmit={submit} className="grid gap-3">
          {mode === "register" && (
            <input
              className="input"
              placeholder="Name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
          <input
            className="input"
            type="email"
            placeholder="Email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="input"
            type="password"
            placeholder="Password (min 8 chars)"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        {error && <p className="mt-3 text-sm text-danger">{error}</p>}

        <button
          className="mt-4 text-sm text-accent hover:underline"
          onClick={() => {
            setMode((m) => (m === "login" ? "register" : "login"));
            setError(null);
          }}
        >
          {mode === "login"
            ? "Need an account? Register"
            : "Have an account? Sign in"}
        </button>
      </div>
    </main>
  );
}

function humanize(raw: string): string {
  if (raw.includes("401")) return "Invalid email or password.";
  if (raw.includes("409")) return "That email is already registered.";
  if (raw.includes("422")) return "Check the email format and password length.";
  return raw.replace(/^Error:\s*/, "");
}
