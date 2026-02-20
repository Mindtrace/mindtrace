"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/context/auth-context";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  const { isAuthenticated, isLoading, refreshUser } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/");
    }
  }, [isLoading, isAuthenticated, router]);

  function handleSuccess() {
    refreshUser();
    router.replace("/");
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (isAuthenticated) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-gradient-to-br from-background via-background to-muted/20 p-4">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Inspectra</h1>
        <p className="text-sm text-muted-foreground">Auth & RBAC</p>
      </div>
      <LoginForm onSuccess={handleSuccess} />
    </div>
  );
}
