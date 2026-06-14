"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TrashIcon } from "@/components/icons";
import { DocumentRead, deleteDocument, listDocuments } from "@/lib/api";

const PENDING_STATES = new Set([
  "pending",
  "parsing",
  "chunking",
  "embedding",
  "indexing",
]);

const STATUS_COLOR: Record<string, string> = {
  completed: "text-ok",
  failed: "text-danger",
};

export function DocumentList({ collectionId }: { collectionId: string }) {
  const qc = useQueryClient();

  const docs = useQuery({
    queryKey: ["documents", collectionId],
    queryFn: () => listDocuments(collectionId),
    // keep polling while anything is still processing
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((d) => PENDING_STATES.has(d.status)) ? 1500 : false;
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", collectionId] }),
  });

  const items = docs.data?.items ?? [];

  if (docs.isLoading) return <p className="text-sm text-muted">Loading documents…</p>;
  if (items.length === 0)
    return <p className="text-sm text-muted">No documents yet. Upload one above.</p>;

  return (
    <div className="grid gap-2">
      {items.map((d) => (
        <DocRow key={d.id} doc={d} onDelete={() => remove.mutate(d.id)} />
      ))}
    </div>
  );
}

function DocRow({ doc, onDelete }: { doc: DocumentRead; onDelete: () => void }) {
  const pending = PENDING_STATES.has(doc.status);
  return (
    <div className="card flex items-center gap-3 p-3">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{doc.filename ?? doc.source_uri}</div>
        <div className="mt-1 flex items-center gap-2 text-xs">
          <span className={STATUS_COLOR[doc.status] ?? "text-muted"}>{doc.status}</span>
          {doc.status === "completed" && (
            <span className="text-muted">· {doc.chunk_count} chunks</span>
          )}
          {doc.error_message && (
            <span className="truncate text-danger" title={doc.error_message}>
              · {doc.error_message}
            </span>
          )}
        </div>
        {pending && (
          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${doc.progress}%` }}
            />
          </div>
        )}
      </div>
      <button
        className="btn-danger btn px-2 py-1.5 text-xs"
        onClick={() => {
          if (confirm(`Delete ${doc.filename ?? "this document"}?`)) onDelete();
        }}
        title="Delete document"
      >
        <TrashIcon className="h-3.5 w-3.5" />
        Delete
      </button>
    </div>
  );
}
