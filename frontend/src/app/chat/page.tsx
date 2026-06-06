"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listCollections } from "@/lib/api";

export default function ChatIndex() {
  const collections = useQuery({ queryKey: ["collections"], queryFn: listCollections });
  const hasCollections = (collections.data?.items.length ?? 0) > 0;

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="max-w-md text-center">
        <h1 className="mb-2 text-2xl font-semibold">Chat with your documents</h1>
        {hasCollections ? (
          <p className="text-muted">
            Pick a collection and hit <span className="text-fg">+ New chat</span> in the
            sidebar to start. Answers stream in with inline citations and auto-eval.
          </p>
        ) : (
          <div className="text-muted">
            <p className="mb-3">
              You don&apos;t have any collections yet. Create one and upload a document to
              get started.
            </p>
            <Link href="/settings/collections" className="btn btn-primary no-underline">
              Manage collections
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
