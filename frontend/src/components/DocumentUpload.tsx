"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ingestFile } from "@/lib/api";

const ACCEPT = ".pdf,.md,.markdown,.txt";

export function DocumentUpload({ collectionId }: { collectionId: string }) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => ingestFile(collectionId, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", collectionId] }),
    onError: (e) => setError(String(e)),
  });

  function handleFiles(files: FileList | null) {
    setError(null);
    if (!files) return;
    for (const f of Array.from(files)) upload.mutate(f);
  }

  return (
    <div>
      <div
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center text-sm transition-colors ${
          dragging ? "border-accent bg-accent/5" : "border-border bg-surface"
        }`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <span className="text-muted">
          {upload.isPending ? "Uploading…" : "Drop a file here or click to upload"}
        </span>
        <span className="mt-1 text-xs text-muted">PDF, Markdown, or plain text</span>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
