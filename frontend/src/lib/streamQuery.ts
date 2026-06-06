// SSE-over-POST. The browser EventSource API can only do GET, but our
// /query/stream endpoint is a POST. So we read the response body as a stream,
// decode it, split on the SSE frame delimiter, and yield typed events.

import { API_BASE, bearerHeaders, Citation } from "./api";

export interface FinalPayload {
  query_id: string;
  answer: string;
  citations: Citation[];
  intent: string | null;
  tools_used: string[];
  latency_ms: number | null;
  model: string | null;
  cache_hit?: boolean;
  cache_hit_kind?: string | null;
}

export type StreamEvent =
  | { type: "tool_start"; data: { name: string; intent?: string; reason?: string } }
  | { type: "tool_end"; data: { name: string; n?: number } }
  | { type: "token"; data: string }
  | { type: "final"; data: FinalPayload }
  | { type: "error"; data: { error: string; query_id?: string } };

export interface StreamRequest {
  collection_id: string;
  question: string;
  conversation_id?: string;
  top_k?: number;
  use_web_search?: boolean;
}

export async function* streamQuery(
  req: StreamRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_BASE}/api/v1/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...bearerHeaders() },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`stream ${res.status}: ${await res.text().catch(() => "")}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const json = line.slice("data:".length).trim();
      if (!json) continue;
      try {
        yield JSON.parse(json) as StreamEvent;
      } catch {
        // skip malformed frame
      }
    }
  }
}
