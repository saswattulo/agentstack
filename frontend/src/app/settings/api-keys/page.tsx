"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PlusIcon } from "@/components/icons";
import {
  ApiKeyCreated,
  createApiKey,
  listApiKeys,
  revokeApiKey,
} from "@/lib/api";

export default function ApiKeysPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);

  const keys = useQuery({ queryKey: ["apiKeys"], queryFn: listApiKeys });

  const create = useMutation({
    mutationFn: () => createApiKey(name.trim() || "key"),
    onSuccess: (k) => {
      setJustCreated(k);
      setName("");
      qc.invalidateQueries({ queryKey: ["apiKeys"] });
    },
  });

  const revoke = useMutation({
    mutationFn: (id: string) => revokeApiKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["apiKeys"] }),
  });

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-1 text-xl font-semibold tracking-tight">API keys</h1>
      <p className="mb-5 text-sm text-muted">
        Machine credentials for scripts and CI. Send as{" "}
        <code>X-API-Key: &lt;key&gt;</code>. Keys inherit your data scope.
      </p>

      <div className="card mb-4 flex items-end gap-2 p-4">
        <div className="flex-1">
          <label className="mb-1 block text-xs text-muted">New key name</label>
          <input
            className="input"
            placeholder="e.g. ci-pipeline"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create.mutate()}
          />
        </div>
        <button
          className="btn btn-primary"
          disabled={create.isPending}
          onClick={() => create.mutate()}
        >
          <PlusIcon className="h-4 w-4" />
          Create key
        </button>
      </div>

      {justCreated && (
        <div className="card mb-4 border-accent/50 p-4">
          <p className="mb-2 text-sm text-ok">
            Key created. Copy it now — you won&apos;t see it again.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 overflow-x-auto whitespace-nowrap rounded bg-surface-2 px-3 py-2 text-xs">
              {justCreated.raw_key}
            </code>
            <button
              className="btn"
              onClick={() => navigator.clipboard?.writeText(justCreated.raw_key)}
            >
              Copy
            </button>
            <button className="btn" onClick={() => setJustCreated(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-2">
        {keys.isLoading && <p className="text-sm text-muted">Loading…</p>}
        {keys.data?.length === 0 && (
          <p className="text-sm text-muted">No API keys yet.</p>
        )}
        {keys.data?.map((k) => (
          <div key={k.id} className="card flex items-center justify-between p-3">
            <div className="min-w-0">
              <div className="text-sm font-medium">
                {k.name}{" "}
                {!k.is_active && <span className="text-xs text-danger">(revoked)</span>}
              </div>
              <div className="mt-0.5 text-xs text-muted">
                <code>{k.key_prefix}…</code> · {k.rate_limit_per_minute}/min ·
                created {new Date(k.created_at).toLocaleDateString()}
                {k.last_used_at &&
                  ` · last used ${new Date(k.last_used_at).toLocaleDateString()}`}
              </div>
            </div>
            {k.is_active && (
              <button
                className="btn btn-danger px-2 py-1 text-xs"
                onClick={() => {
                  if (confirm(`Revoke "${k.name}"? Any client using it stops working.`))
                    revoke.mutate(k.id);
                }}
              >
                Revoke
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
