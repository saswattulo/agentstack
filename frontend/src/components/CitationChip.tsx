"use client";

import { useState } from "react";
import { Citation } from "@/lib/api";

export function CitationChip({ n, citation }: { n: number; citation?: Citation }) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-block align-baseline">
      <button
        className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full border border-accent/50 bg-accent/10 px-1 text-[10px] font-medium leading-none text-accent hover:bg-accent/20"
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        title={citation ? `Source ${n}` : `Citation ${n}`}
      >
        {n}
      </button>
      {open && citation && (
        <span className="absolute bottom-full left-1/2 z-10 mb-1 w-72 -translate-x-1/2 rounded-md border border-border bg-surface-2 p-2 text-xs text-fg shadow-lg">
          <span className="mb-1 block text-[10px] uppercase tracking-wide text-muted">
            Source {n}
            {citation.score != null ? ` · score ${citation.score.toFixed(3)}` : ""}
          </span>
          <span className="block max-h-32 overflow-y-auto whitespace-pre-wrap text-muted">
            {citation.preview}
          </span>
        </span>
      )}
    </span>
  );
}
