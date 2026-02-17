"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { getToken, clearToken } from "@/lib/api/client";
import { getMe, logout as logoutApi } from "@/lib/api/auth";
import type { User } from "@/lib/api/types";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: () => Promise<void>;
  logout: () => void;
  refetchUser: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | undefined>(
  undefined
);

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = React.useState<User | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const router = useRouter();

  const fetchUser = React.useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const userData = await getMe();
      setUser(userData);
    } catch (error) {
      // Token is invalid or expired
      console.error("Failed to fetch user:", error);
      clearToken();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch user on mount
  React.useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const login = React.useCallback(async () => {
    // This is called after successful login to refresh user data
    setIsLoading(true);
    await fetchUser();
    router.push("/dashboard");
  }, [fetchUser, router]);

  const logout = React.useCallback(() => {
    logoutApi();
    setUser(null);
    router.push("/login");
  }, [router]);

  const refetchUser = React.useCallback(async () => {
    await fetchUser();
  }, [fetchUser]);

  const value = React.useMemo(
    () => ({
      user,
      isLoading,
      isAuthenticated: !!user,
      login,
      logout,
      refetchUser,
    }),
    [user, isLoading, login, logout, refetchUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
