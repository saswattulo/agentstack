"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import {
  BookIcon,
  CheckIcon,
  KeyIcon,
  LogoIcon,
  LogOutIcon,
  MicIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
} from "@/components/icons";
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
      <div className="flex items-center justify-between px-4 py-3.5">
        <Link
          href="/chat"
          className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-fg no-underline"
        >
          <LogoIcon className="h-5 w-5 text-accent" />
          AgentStack
        </Link>
        <span className="chip" title="Use the mic button in a chat to talk">
          <MicIcon className="h-3 w-3" />
          Voice
        </span>
      </div>

      <div className="px-3 pb-3">
        <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-muted">
          Collection
        </label>
        <select
          className="input mb-2.5"
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
          className="btn btn-primary w-full"
          disabled={!activeCollection || newChat.isPending}
          onClick={() => newChat.mutate()}
        >
          <PlusIcon className="h-4 w-4" />
          New chat
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        <p className="px-2 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted">
          Conversations
        </p>
        {conversations.isLoading && <p className="px-2 text-sm text-muted">Loading…</p>}
        {(conversations.data?.items ?? []).map((conv) => (
          <ConversationRow
            key={conv.id}
            conv={conv}
            active={params?.conversationId === conv.id}
          />
        ))}
        {conversations.data?.items.length === 0 && (
          <p className="px-2 py-3 text-sm text-muted">No conversations yet.</p>
        )}
      </div>

      <nav className="border-t border-border p-2 text-sm">
        <SideLink
          href="/settings/collections"
          active={pathname?.startsWith("/settings/collections")}
          icon={<BookIcon className="h-4 w-4" />}
        >
          Collections
        </SideLink>
        <SideLink
          href="/settings/api-keys"
          active={pathname?.startsWith("/settings/api-keys")}
          icon={<KeyIcon className="h-4 w-4" />}
        >
          API keys
        </SideLink>
        <div className="mt-1 flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
          <span className="truncate text-muted" title={user?.email}>
            {user?.email}
          </span>
          <button
            className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-muted transition-colors hover:bg-surface-2 hover:text-danger"
            onClick={logout}
            title="Log out"
          >
            <LogOutIcon className="h-3.5 w-3.5" />
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
  icon,
  children,
}: {
  href: string;
  active?: boolean;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 font-medium no-underline transition-colors ${
        active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"
      }`}
    >
      {icon}
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
        <button className="icon-btn shrink-0" onClick={() => rename.mutate()} title="Save">
          <CheckIcon className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      className={`group flex items-center justify-between rounded-md px-2 py-1.5 transition-colors ${
        active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"
      }`}
    >
      <Link
        href={`/chat/${conv.id}`}
        className="min-w-0 flex-1 truncate text-sm text-current no-underline"
        title={conv.title}
      >
        {conv.title}
      </Link>
      <div className="ml-1 hidden shrink-0 items-center gap-0.5 group-hover:flex">
        <button
          className="icon-btn h-6 w-6"
          onClick={() => {
            setTitle(conv.title);
            setEditing(true);
          }}
          title="Rename"
        >
          <PencilIcon className="h-3.5 w-3.5" />
        </button>
        <button
          className="icon-btn h-6 w-6 hover:text-danger"
          onClick={() => {
            if (confirm(`Delete "${conv.title}"?`)) remove.mutate();
          }}
          title="Delete"
        >
          <TrashIcon className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
