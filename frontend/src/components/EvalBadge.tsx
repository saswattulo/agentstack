"use client";

import { useQuery } from "@tanstack/react-query";
import { getEvalResult } from "@/lib/api";

function Bar({ label, value }: { label: string; value: number | null }) {
  const pct = value == null ? 0 : Math.round(value * 100);
  const color =
    value == null ? "bg-border" : pct >= 70 ? "bg-ok" : pct >= 40 ? "bg-accent" : "bg-danger";
  return (
    <div className="flex items-center gap-2" title={`${label}: ${value == null ? "—" : value.toFixed(2)}`}>
      <span className="w-20 shrink-0 text-[10px] text-muted">{label}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <span className={`block h-full ${color}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="w-7 shrink-0 text-right text-[10px] tabular-nums text-muted">
        {value == null ? "—" : pct}
      </span>
    </div>
  );
}

export function EvalBadge({ queryId }: { queryId: string }) {
  const q = useQuery({
    queryKey: ["eval", queryId],
    queryFn: () => getEvalResult(queryId),
    // eval runs async on the worker; poll until it lands or we give up
    refetchInterval: (query) => (query.state.data ? false : 4000),
    refetchIntervalInBackground: true,
    retry: false,
    staleTime: Infinity,
  });

  if (!q.data) {
    return <span className="text-[10px] text-muted">scoring…</span>;
  }

  return (
    <div className="mt-2 grid gap-1 rounded-md border border-border bg-surface p-2">
      <Bar label="faithful" value={q.data.faithfulness} />
      <Bar label="relevancy" value={q.data.answer_relevancy} />
      <Bar label="citations" value={q.data.citation_accuracy} />
    </div>
  );
}
