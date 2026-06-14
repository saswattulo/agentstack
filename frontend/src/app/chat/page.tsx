"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BookIcon, LogoIcon } from "@/components/icons";
import { listCollections } from "@/lib/api";

export default function ChatIndex() {
  const collections = useQuery({ queryKey: ["collections"], queryFn: listCollections });
  const hasCollections = (collections.data?.items.length ?? 0) > 0;

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="max-w-md text-center">
        <span className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/30 bg-accent/10">
          <LogoIcon className="h-7 w-7 text-accent" />
        </span>
        <h1 className="mb-2 text-2xl font-semibold tracking-tight">Chat with your documents</h1>
        {hasCollections ? (
          <p className="text-muted">
            Pick a collection and hit{" "}
            <span className="font-medium text-fg">New chat</span> in the sidebar to start.
            Answers stream in with inline citations and auto-eval.
          </p>
        ) : (
          <div className="text-muted">
            <p className="mb-4">
              You don&apos;t have any collections yet. Create one and upload a document to
              get started.
            </p>
            <Link href="/settings/collections" className="btn btn-primary no-underline">
              <BookIcon className="h-4 w-4" />
              Manage collections
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
