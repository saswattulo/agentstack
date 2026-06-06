"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/AuthProvider";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/chat" : "/login");
  }, [user, loading, router]);

  return (
    <div className="flex h-screen items-center justify-center text-muted">
      Loading…
    </div>
  );
}
