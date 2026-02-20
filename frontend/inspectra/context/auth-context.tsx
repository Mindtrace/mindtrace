"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { getMe, logout as apiLogout } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const initialAuthDone = useRef(false);

  const refreshUser = useCallback(async () => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("inspectra_token")
        : null;
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const me = await getMe();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialAuthDone.current) return;
    initialAuthDone.current = true;
    refreshUser();
  }, [refreshUser]);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
  }, []);

  const value: AuthContextValue = {
    user,
    isLoading,
    isAuthenticated: !!user,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
