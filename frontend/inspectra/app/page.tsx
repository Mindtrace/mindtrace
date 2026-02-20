"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/context/auth-context";

export default function Home() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (isAuthenticated) {
      router.replace(
        user?.role === "super_admin" ? "/organizations" : "/users"
      );
    } else {
      router.replace("/login");
    }
  }, [user?.role, isAuthenticated, isLoading, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}
