"use client";

import { useState } from "react";

export function ChatComposer({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");

  function submit() {
    const t = text.trim();
    if (!t || disabled) return;
    onSend(t);
    setText("");
  }

  return (
    <div className="border-t border-border bg-surface p-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          className="input max-h-40 min-h-[2.5rem] flex-1 resize-none"
          rows={1}
          placeholder="Ask about your documents… (Enter to send, Shift+Enter for newline)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="btn btn-primary" disabled={disabled || !text.trim()} onClick={submit}>
          Send
        </button>
      </div>
    </div>
  );
}
