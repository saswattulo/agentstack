"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEvalResult } from "@/lib/api";
import { ChevronDownIcon, ChevronRightIcon } from "./icons";

function Bar({ label, value }: { label: string; value: number | null | undefined }) {
  const has = value != null;
  const pct = has ? Math.round(value * 100) : 0;
  const color =
    !has ? "bg-border" : pct >= 70 ? "bg-ok" : pct >= 40 ? "bg-accent" : "bg-danger";
  return (
    <div className="flex items-center gap-2" title={`${label}: ${has ? value.toFixed(2) : "—"}`}>
      <span className="w-20 shrink-0 text-[10px] text-muted">{label}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <span className={`block h-full ${color}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="w-7 shrink-0 text-right text-[10px] tabular-nums text-muted">
        {has ? pct : "—"}
      </span>
    </div>
  );
}

const MAX_POLLS = 20; // ~80s; eval normally lands in 20-40s

export function EvalBadge({ queryId }: { queryId: string }) {
  // Collapsed by default — eval is opt-in. We only fetch once the user opens
  // it (enabled: open), so closed answers make zero eval requests.
  const [open, setOpen] = useState(false);

  const q = useQuery({
    queryKey: ["eval", queryId],
    queryFn: () => getEvalResult(queryId),
    enabled: open,
    refetchInterval: (query) => {
      if (query.state.data?.status === "ready") return false;
      if ((query.state.dataUpdateCount ?? 0) >= MAX_POLLS) return false;
      return 4000;
    },
    staleTime: Infinity,
  });

  const ready = q.data?.status === "ready";

  return (
    <div className="mt-1">
      <button
        className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted transition-colors hover:text-fg"
        onClick={() => setOpen((o) => !o)}
        title="RAGAS eval scores for this answer"
      >
        {open ? (
          <ChevronDownIcon className="h-3 w-3" />
        ) : (
          <ChevronRightIcon className="h-3 w-3" />
        )}
        eval scores
      </button>

      {open &&
        (ready ? (
          <div className="mt-1 grid gap-1 rounded-md border border-border bg-surface p-2">
            <Bar label="faithful" value={q.data?.faithfulness} />
            <Bar label="relevancy" value={q.data?.answer_relevancy} />
            <Bar label="citations" value={q.data?.citation_accuracy} />
          </div>
        ) : (
          <span className="ml-3 text-[10px] text-muted">scoring…</span>
        ))}
    </div>
  );
}
