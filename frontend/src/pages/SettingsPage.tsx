import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Copy } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { api } from "../api/client";
import type { components } from "../api/types";
import { calendarDate } from "../lib/format";

type ApiKey = components["schemas"]["ApiKeyOut"];
type CreatedKey = components["schemas"]["ApiKeyCreated"];
type KeyType = "read_only" | "full_access";

const FULL_ACCESS_WARNING =
  "Anyone with this key can read and change all donor data, including contact details. " +
  "Share only with apps you trust; revoke when done.";
const KEYS = ["settings", "api-keys"] as const;

function useApiKeys() {
  return useQuery({
    queryKey: KEYS,
    queryFn: ({ signal }) => api<{ items: ApiKey[] }>("/api-keys", { signal }),
    retry: false,
  });
}

function useCreateKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { name: string; type: KeyType }) =>
      api<CreatedKey>("/api-keys", {
        method: "POST",
        body: {
          name: v.name,
          scopes: [v.type === "full_access" ? "full_access" : "read:aggregates"],
        },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS }),
  });
}

function useRevokeKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<ApiKey>(`/api-keys/${id}/revoke`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS }),
  });
}

function NewKey({ made, onDone }: { made: CreatedKey; onDone: () => void }) {
  const [copied, setCopied] = useState<"yes" | "failed" | null>(null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(made.key);
      setCopied("yes");
    } catch {
      setCopied("failed");
    }
  }
  return (
    <section
      aria-labelledby="new-key-title"
      className="mt-6 rounded-lg border border-rule bg-surface p-4"
    >
      <h3 id="new-key-title" className="font-semibold">
        Key created: {made.name}
      </h3>
      <p className="mt-1 text-ink-muted">
        This is the only time the whole key is shown. Copy it now and store it somewhere safe.
      </p>
      <p className="mt-3 flex flex-wrap items-center gap-3">
        <code className="break-all rounded bg-wash px-2 py-1" data-testid="new-key">
          {made.key}
        </code>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-2 rounded-md border border-control-border px-3 py-2"
        >
          {copied === "yes" ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
          {copied === "yes" ? "Copied" : "Copy key"}
        </button>
      </p>
      <p role="status" className="mt-1 text-ink-muted">
        {copied === "failed" && "Your browser blocked copying. Select the key and copy it by hand."}
      </p>
      <button
        type="button"
        onClick={onDone}
        className="mt-3 rounded-md bg-forest px-4 py-2 font-medium text-white hover:bg-forest-hover"
      >
        I have saved it
      </button>
    </section>
  );
}

function KeyForm({ onCreated }: { onCreated: (k: CreatedKey) => void }) {
  const create = useCreateKey();
  const [name, setName] = useState("");
  const [type, setType] = useState<KeyType>("read_only");

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      { name: name.trim(), type },
      {
        onSuccess: (k) => {
          setName("");
          setType("read_only");
          onCreated(k);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="mt-4 max-w-xl space-y-4">
      <div>
        <label htmlFor="key-name" className="block font-medium">
          Name
        </label>
        <input
          id="key-name"
          required
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="What will use this key?"
          className="mt-1 w-full rounded-md border border-control-border bg-surface px-3 py-2"
        />
      </div>
      <fieldset>
        <legend className="font-medium">Access</legend>
        <label className="mt-1 flex items-start gap-2">
          <input
            type="radio"
            name="key-type"
            checked={type === "read_only"}
            onChange={() => setType("read_only")}
            className="mt-1"
          />
          <span>
            Read-only totals
            <span className="secondary-text">Aggregate numbers on /api/v1. No donor details.</span>
          </span>
        </label>
        <label className="mt-2 flex items-start gap-2">
          <input
            type="radio"
            name="key-type"
            checked={type === "full_access"}
            onChange={() => setType("full_access")}
            className="mt-1"
          />
          <span>
            Full access
            <span className="secondary-text">
              Every /api/app route, as you, with no login. Expires in 90 days.
            </span>
          </span>
        </label>
      </fieldset>
      {type === "full_access" && (
        <p
          role="note"
          className="flex items-start gap-2 rounded-md border border-danger bg-danger-wash p-3 font-medium text-danger"
        >
          <AlertTriangle size={18} aria-hidden className="mt-0.5" />
          <span>
            <span className="sr-only">Warning: </span>
            {FULL_ACCESS_WARNING}
          </span>
        </p>
      )}
      {create.error && (
        <p role="alert" className="rounded-md bg-danger-wash p-3 text-danger">
          {create.error.message}
        </p>
      )}
      <button
        type="submit"
        disabled={create.isPending}
        className="rounded-md bg-forest px-4 py-2 font-medium text-white hover:bg-forest-hover disabled:opacity-60"
      >
        {create.isPending ? "Creating…" : "Create key"}
      </button>
    </form>
  );
}

function KeyList({ items }: { items: ApiKey[] }) {
  const revoke = useRevokeKey();
  if (items.length === 0) return <p className="mt-4 text-ink-muted">No API keys yet.</p>;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[44rem] text-left">
        <caption className="sr-only">API keys</caption>
        <thead>
          <tr className="border-b border-rule text-ink-muted">
            <th scope="col" className="py-2 pr-3">
              Name
            </th>
            <th scope="col" className="py-2 pr-3">
              Type
            </th>
            <th scope="col" className="py-2 pr-3">
              Key starts
            </th>
            <th scope="col" className="py-2 pr-3">
              Created by
            </th>
            <th scope="col" className="py-2 pr-3">
              Created
            </th>
            <th scope="col" className="py-2 pr-3">
              Last used
            </th>
            <th scope="col" className="py-2 pr-3">
              Expires
            </th>
            <th scope="col" className="py-2">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((k) => (
            <tr key={k.id} className="border-b border-rule align-top">
              <td className="py-2 pr-3">{k.name}</td>
              <td className="py-2 pr-3">
                {k.type === "full_access" ? (
                  <strong className="text-danger">Full access</strong>
                ) : (
                  "Read-only"
                )}
              </td>
              <td className="py-2 pr-3">
                <code>{k.prefix}…</code>
              </td>
              <td className="py-2 pr-3">{k.created_by_name ?? "Unknown"}</td>
              <td className="py-2 pr-3">{calendarDate(k.created_at)}</td>
              <td className="py-2 pr-3">{calendarDate(k.last_used_at, "Never")}</td>
              <td className="py-2 pr-3">{calendarDate(k.expires_at, "Never")}</td>
              <td className="py-2">
                {k.revoked_at ? (
                  `Revoked ${calendarDate(k.revoked_at)}`
                ) : (
                  <button
                    type="button"
                    disabled={revoke.isPending}
                    onClick={() => {
                      if (window.confirm(`Revoke "${k.name}"? Apps using it stop working now.`))
                        revoke.mutate(k.id);
                    }}
                    className="rounded-md border border-danger px-3 py-1 text-danger"
                  >
                    Revoke<span className="sr-only"> {k.name}</span>
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {revoke.error && (
        <p role="alert" className="mt-3 rounded-md bg-danger-wash p-3 text-danger">
          {revoke.error.message}
        </p>
      )}
    </div>
  );
}

export function SettingsPage() {
  const keys = useApiKeys();
  const [made, setMade] = useState<CreatedKey | null>(null);
  useEffect(() => {
    document.title = "Settings · CIC Compass";
  }, []);

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title" className="text-2xl font-semibold">
        Settings
      </h1>
      <h2 className="mt-6 text-xl font-semibold">API keys</h2>
      <p className="mt-1 max-w-2xl text-ink-muted">
        Let another app connect to Compass. Keys are shown once and can be revoked at any time.
      </p>
      {made ? <NewKey made={made} onDone={() => setMade(null)} /> : <KeyForm onCreated={setMade} />}
      {keys.error && (
        <p role="alert" className="mt-4 rounded-md bg-danger-wash p-3 text-danger">
          {keys.error.message}
        </p>
      )}
      {keys.data && <KeyList items={keys.data.items} />}
    </section>
  );
}
