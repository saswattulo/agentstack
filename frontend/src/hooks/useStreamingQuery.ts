"use client";

import { useCallback, useRef, useState } from "react";
import { Citation } from "@/lib/api";
import { FinalPayload, StreamRequest, streamQuery } from "@/lib/streamQuery";

export interface StreamingState {
  streaming: boolean;
  question: string | null;
  partialAnswer: string;
  status: string | null; // "retrieving…" / "searching the web…"
  citations: Citation[];
  final: FinalPayload | null;
  error: string | null;
}

const IDLE: StreamingState = {
  streaming: false,
  question: null,
  partialAnswer: "",
  status: null,
  citations: [],
  final: null,
  error: null,
};

const TOOL_LABEL: Record<string, string> = {
  router: "routing…",
  retrieve: "retrieving…",
  web_search: "searching the web…",
};

export function useStreamingQuery() {
  const [state, setState] = useState<StreamingState>(IDLE);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => setState(IDLE), []);

  const send = useCallback(async (req: StreamRequest): Promise<FinalPayload | null> => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setState({ ...IDLE, streaming: true, question: req.question, status: "thinking…" });

    let answer = "";
    let finalPayload: FinalPayload | null = null;

    try {
      for await (const ev of streamQuery(req, ac.signal)) {
        if (ev.type === "tool_start") {
          const label = TOOL_LABEL[ev.data.name] ?? `${ev.data.name}…`;
          setState((s) => ({ ...s, status: label }));
        } else if (ev.type === "token") {
          answer += ev.data;
          setState((s) => ({ ...s, partialAnswer: answer, status: null }));
        } else if (ev.type === "final") {
          finalPayload = ev.data;
          setState((s) => ({
            ...s,
            streaming: false,
            partialAnswer: ev.data.answer || answer,
            citations: ev.data.citations || [],
            final: ev.data,
            status: null,
          }));
        } else if (ev.type === "error") {
          setState((s) => ({ ...s, streaming: false, error: ev.data.error, status: null }));
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setState((s) => ({ ...s, streaming: false, error: String(e), status: null }));
      }
    }

    return finalPayload;
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => ({ ...s, streaming: false, status: null }));
  }, []);

  return { state, send, cancel, reset };
}
