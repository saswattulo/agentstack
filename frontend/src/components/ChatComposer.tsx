"use client";

import { useState } from "react";

export function ChatComposer({
  onSend,
  disabled,
  recording,
  speaking,
  onMicToggle,
  onStopSpeaking,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  recording?: boolean;
  speaking?: boolean;
  onMicToggle?: () => void;
  onStopSpeaking?: () => void;
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
        {onMicToggle && (
          <button
            className={`btn shrink-0 ${recording ? "border-danger/60 text-danger" : ""}`}
            onClick={onMicToggle}
            title={recording ? "Stop microphone" : "Start talking"}
          >
            {recording ? (
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-danger" />
                Mic
              </span>
            ) : (
              "🎙"
            )}
          </button>
        )}

        <textarea
          className="input max-h-40 min-h-[2.5rem] flex-1 resize-none"
          rows={1}
          placeholder={
            recording
              ? "Listening… speak, or type to ask silently"
              : "Ask about your documents… (Enter to send, Shift+Enter for newline)"
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />

        {speaking && onStopSpeaking ? (
          <button className="btn btn-danger shrink-0" onClick={onStopSpeaking} title="Stop the agent">
            ⏹ Stop
          </button>
        ) : (
          <button className="btn btn-primary shrink-0" disabled={disabled || !text.trim()} onClick={submit}>
            Send
          </button>
        )}
      </div>
    </div>
  );
}
