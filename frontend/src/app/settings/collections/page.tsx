"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { DocumentList } from "@/components/DocumentList";
import { DocumentUpload } from "@/components/DocumentUpload";
import { ChevronDownIcon, ChevronRightIcon, PlusIcon, TrashIcon } from "@/components/icons";
import {
  Collection,
  createCollection,
  deleteCollection,
  listCollections,
} from "@/lib/api";

export default function CollectionsPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const collections = useQuery({ queryKey: ["collections"], queryFn: listCollections });

  const remove = useMutation({
    mutationFn: (id: string) => deleteCollection(id),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["collections"] });
      if (selected === id) setSelected(null);
    },
  });

  const items = collections.data?.items ?? [];

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Collections</h1>
          <p className="mt-0.5 text-sm text-muted">
            Group your documents into searchable, per-collection knowledge bases.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          <PlusIcon className="h-4 w-4" />
          New collection
        </button>
      </div>

      {creating && (
        <CreateCollectionForm
          onClose={() => setCreating(false)}
          onCreated={(c) => {
            setCreating(false);
            setSelected(c.id);
          }}
        />
      )}

      <div className="grid gap-2">
        {items.length === 0 && !collections.isLoading && (
          <p className="text-sm text-muted">No collections yet. Create one to begin.</p>
        )}
        {items.map((c) => (
          <div key={c.id} className="card overflow-hidden">
            <button
              className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-surface-2"
              onClick={() => setSelected(selected === c.id ? null : c.id)}
            >
              <span>
                <span className="font-medium">{c.name}</span>
                {c.description && (
                  <span className="ml-2 text-sm text-muted">{c.description}</span>
                )}
                <span className="ml-2 text-xs text-muted">· {c.chunking_strategy}</span>
              </span>
              {selected === c.id ? (
                <ChevronDownIcon className="h-4 w-4 shrink-0 text-muted" />
              ) : (
                <ChevronRightIcon className="h-4 w-4 shrink-0 text-muted" />
              )}
            </button>

            {selected === c.id && (
              <div className="border-t border-border p-4">
                <DocumentUpload collectionId={c.id} />
                <div className="mt-4">
                  <DocumentList collectionId={c.id} />
                </div>
                <div className="mt-4 flex justify-end">
                  <button
                    className="btn btn-danger"
                    onClick={() => {
                      if (
                        confirm(
                          `Delete collection "${c.name}" and all its documents? This cannot be undone.`,
                        )
                      )
                        remove.mutate(c.id);
                    }}
                  >
                    <TrashIcon className="h-4 w-4" />
                    Delete collection
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function CreateCollectionForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (c: Collection) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => createCollection(name.trim(), description.trim() || undefined),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["collections"] });
      onCreated(c);
    },
    onError: (e) => setError(humanize(String(e))),
  });

  return (
    <div className="card mb-4 p-4">
      <div className="grid gap-2">
        <input
          className="input"
          placeholder="Collection name"
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="input"
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        {error && <p className="text-xs text-danger">{error}</p>}
        <div className="flex gap-2">
          <button
            className="btn btn-primary"
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Create
          </button>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function humanize(raw: string): string {
  if (raw.includes("409")) return "You already have a collection with that name.";
  return raw.replace(/^Error:\s*/, "");
}
