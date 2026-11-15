import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { components } from "../api/types";
import "../components/quick-note.css";
import "./settings.css";

export function InvitePage() {
  const { token } = useParams();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  useEffect(() => {
    document.title = "Join the board · CIC Compass";
  }, []);
  const accept = useMutation({
    retry: false,
    gcTime: 0,
    mutationFn: async () => {
      await api<components["schemas"]["MeOut"]>(
        `/auth/invite/${encodeURIComponent(token ?? "")}/accept`,
        {
          method: "POST",
          body: {
            display_name: name.trim(),
            password,
          } satisfies components["schemas"]["InviteAcceptIn"],
        },
      );
    },
    onSuccess: () => {
      setDone(true);
      setPassword("");
      // Remove the consumed secret from this history entry without navigating away from success.
      window.history.replaceState(window.history.state, "", "/invite/accepted");
    },
  });
  const invalid = accept.error instanceof ApiError && accept.error.status === 400;
  return (
    <main className="invite-entry">
      <p className="eyebrow">Coding in Color / CIC Compass</p>
      <h1>{done ? "Welcome to the circle." : "Care starts with you."}</h1>
      {done ? (
        <>
          <p role="status">
            Your board-member account is ready. Sign in with your invited email and the password you
            just chose.
          </p>
          <Link className="button" to="/login" replace>
            Sign in to Compass
          </Link>
        </>
      ) : (
        <>
          <p>
            Accept your private invitation to help steward Coding in Color’s relationships. Each
            link is valid once, for 72 hours.
          </p>
          <form
            aria-busy={accept.isPending}
            onSubmit={(e) => {
              e.preventDefault();
              if (!accept.isPending && name.trim() && token && !invalid) accept.mutate();
            }}
          >
            <label className="note-field" htmlFor="join-name">
              Your name
              <input
                id="join-name"
                autoComplete="name"
                required
                maxLength={100}
                value={name}
                disabled={accept.isPending || invalid}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="note-field" htmlFor="join-password">
              Choose a password
              <span className="secondary-text" id="join-password-help">
                Use at least 12 characters.
              </span>
              <input
                id="join-password"
                type="password"
                autoComplete="new-password"
                aria-describedby="join-password-help"
                required
                minLength={12}
                maxLength={256}
                value={password}
                disabled={accept.isPending || invalid}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {accept.error && (
              <p role="alert" className="save-error">
                {invalid
                  ? "This invitation is invalid, expired, or already used. Ask a board member with invitation access for a new link."
                  : accept.error instanceof ApiError && accept.error.status === 501
                    ? "Joining is not available on the server yet."
                    : "We could not confirm your account. Your entries are kept here. Try again; if the link was used, sign in with your chosen password."}
              </p>
            )}
            <button className="button" disabled={accept.isPending || invalid || !name.trim()}>
              {accept.isPending ? "Creating your account…" : "Join the board"}
            </button>
            <Link to="/login">Already joined? Sign in</Link>
          </form>
        </>
      )}
    </main>
  );
}
