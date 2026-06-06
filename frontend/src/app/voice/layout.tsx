"use client";

import { RequireAuth } from "@/components/RequireAuth";
import { Sidebar } from "@/components/Sidebar";

export default function VoiceLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex h-screen">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </RequireAuth>
  );
}
