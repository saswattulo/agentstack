"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import {
  Conversation,
  createConversation,
  deleteConversation,
  listCollections,
  listConversations,
  updateConversation,
} from "@/lib/api";

const LS_COLLECTION = "agentstack.activeCollection";

export function Sidebar() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams<{ conversationId?: string }>();
  const { user, logout } = useAuth();

  const [activeCollection, setActiveCollection] = useState<string>("");

  const collections = useQuery({
    queryKey: ["collections"],
    queryFn: listCollections,
  });

  const conversations = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });

  // hydrate / default the active collection
  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem(LS_COLLECTION) : null;
    const items = collections.data?.items ?? [];
    if (saved && items.some((c) => c.id === saved)) setActiveCollection(saved);
    else if (items[0]) setActiveCollection(items[0].id);
  }, [collections.data]);

  function pickCollection(id: string) {
    setActiveCollection(id);
    localStorage.setItem(LS_COLLECTION, id);
  }

  const newChat = useMutation({
    mutationFn: () => createConversation("New chat", activeCollection || undefined),
    onSuccess: (conv) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      router.push(`/chat/${conv.id}`);
    },
  });

  return (
    <aside className="flex h-screen w-72 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center justify-between p-3">
        <Link href="/chat" className="text-base font-semibold text-fg no-underline">
          AgentStack
        </Link>
        <Link href="/voice" className="chip no-underline" title="Voice agent">
          🎙 voice
        </Link>
      </div>

      <div className="px-3">
        <label className="mb-1 block text-xs text-muted">Collection</label>
        <select
          className="input mb-2"
          value={activeCollection}
          onChange={(e) => pickCollection(e.target.value)}
        >
          {(collections.data?.items ?? []).length === 0 && (
            <option value="">No collections yet</option>
          )}
          {(collections.data?.items ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          className="btn btn-primary mb-3 w-full"
          disabled={!activeCollection || newChat.isPending}
          onClick={() => newChat.mutate()}
        >
          + New chat
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        {conversations.isLoading && <p className="px-2 text-sm text-muted">Loading…</p>}
        {(conversations.data?.items ?? []).map((conv) => (
          <ConversationRow
            key={conv.id}
            conv={conv}
            active={params?.conversationId === conv.id}
          />
        ))}
        {conversations.data?.items.length === 0 && (
          <p className="px-2 py-4 text-sm text-muted">No conversations yet.</p>
        )}
      </div>

      <nav className="border-t border-border p-2 text-sm">
        <SideLink href="/settings/collections" active={pathname?.startsWith("/settings/collections")}>
          📚 Collections
        </SideLink>
        <SideLink href="/settings/api-keys" active={pathname?.startsWith("/settings/api-keys")}>
          🔑 API keys
        </SideLink>
        <div className="mt-2 flex items-center justify-between px-2 py-1 text-xs text-muted">
          <span className="truncate">{user?.email}</span>
          <button className="text-danger hover:underline" onClick={logout}>
            Logout
          </button>
        </div>
      </nav>
    </aside>
  );
}

function SideLink({
  href,
  active,
  children,
}: {
  href: string;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`block rounded-md px-2 py-1.5 no-underline ${
        active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"
      }`}
    >
      {children}
    </Link>
  );
}

function ConversationRow({ conv, active }: { conv: Conversation; active: boolean }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(conv.title);

  const rename = useMutation({
    mutationFn: () => updateConversation(conv.id, title.trim() || "Untitled"),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteConversation(conv.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (active) router.push("/chat");
    },
  });

  if (editing) {
    return (
      <div className="flex items-center gap-1 px-1 py-1">
        <input
          className="input py-1 text-sm"
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") rename.mutate();
            if (e.key === "Escape") setEditing(false);
          }}
        />
        <button className="btn px-2 py-1 text-xs" onClick={() => rename.mutate()}>
          ✓
        </button>
      </div>
    );
  }

  return (
    <div
      className={`group flex items-center justify-between rounded-md px-2 py-1.5 ${
        active ? "bg-surface-2" : "hover:bg-surface-2"
      }`}
    >
      <Link
        href={`/chat/${conv.id}`}
        className="min-w-0 flex-1 truncate text-sm text-fg no-underline"
        title={conv.title}
      >
        {conv.title}
      </Link>
      <div className="ml-1 hidden shrink-0 gap-1 group-hover:flex">
        <button
          className="text-xs text-muted hover:text-fg"
          onClick={() => {
            setTitle(conv.title);
            setEditing(true);
          }}
          title="Rename"
        >
          ✎
        </button>
        <button
          className="text-xs text-muted hover:text-danger"
          onClick={() => {
            if (confirm(`Delete "${conv.title}"?`)) remove.mutate();
          }}
          title="Delete"
        >
          🗑
        </button>
      </div>
    </div>
  );
}
