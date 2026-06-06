"use client";

import { Fragment, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Citation } from "@/lib/api";
import { CitationChip } from "./CitationChip";

// qwen3 emits <think>…</think>; strip it before rendering.
function stripThink(text: string): string {
  return text.replace(/<think>[\s\S]*?<\/think>/g, "").replace(/<think>[\s\S]*$/g, "").trim();
}

// Replace [n] markers inside a text node with CitationChip components.
function withCitations(text: string, citations: Citation[]): ReactNode[] {
  const byIndex = new Map(citations.map((c) => [c.index, c]));
  const parts: ReactNode[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(<Fragment key={key++}>{text.slice(last, m.index)}</Fragment>);
    const n = parseInt(m[1], 10);
    parts.push(<CitationChip key={key++} n={n} citation={byIndex.get(n)} />);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(<Fragment key={key++}>{text.slice(last)}</Fragment>);
  return parts;
}

function renderChildren(children: ReactNode, citations: Citation[]): ReactNode {
  if (typeof children === "string") return withCitations(children, citations);
  if (Array.isArray(children))
    return children.map((c, i) =>
      typeof c === "string" ? <Fragment key={i}>{withCitations(c, citations)}</Fragment> : c,
    );
  return children;
}

export function AnswerMarkdown({
  text,
  citations,
}: {
  text: string;
  citations: Citation[];
}) {
  const clean = stripThink(text);
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{renderChildren(children, citations)}</p>,
          li: ({ children }) => <li>{renderChildren(children, citations)}</li>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {clean}
      </ReactMarkdown>
    </div>
  );
}
