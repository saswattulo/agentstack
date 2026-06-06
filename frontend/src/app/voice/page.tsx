"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Voice now lives inside the chat thread (mic button in the composer).
// Keep this route as a redirect so old links don't 404.
export default function VoiceRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/chat");
  }, [router]);
  return (
    <div className="flex h-full items-center justify-center text-muted">
      Voice is now in chat — redirecting…
    </div>
  );
}
