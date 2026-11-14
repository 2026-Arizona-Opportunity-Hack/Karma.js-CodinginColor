import { type FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useLogin, useMe } from "../hooks/useAuth";

export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (me.data) return <Navigate to={from} replace />;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    login.mutate({ email, password });
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-slate-900">CIC Compass</h1>
        <p className="mt-1 text-sm text-slate-600">Sign in with your board member account.</p>
        <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-800">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-400 px-3 py-2 text-slate-900"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-800">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-400 px-3 py-2 text-slate-900"
            />
          </div>
          {login.error && (
            <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">
              {login.error.message}
            </p>
          )}
          <button
            type="submit"
            disabled={login.isPending}
            className="w-full rounded-md bg-indigo-700 px-4 py-2 font-medium text-white hover:bg-indigo-800 disabled:opacity-60"
          >
            {login.isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
