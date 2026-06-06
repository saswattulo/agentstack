"use client";

import { RequireAuth } from "@/components/RequireAuth";
import { Sidebar } from "@/components/Sidebar";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex h-screen">
        <Sidebar />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </RequireAuth>
  );
}
