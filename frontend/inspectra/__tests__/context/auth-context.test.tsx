import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "@/context/auth-context";
import * as api from "@/lib/api/client";

jest.mock("@/lib/api/client", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
}));

function Consumer() {
  const { user, isLoading, isAuthenticated, logout, refreshUser } = useAuth();
  if (isLoading) return <span>Loading</span>;
  return (
    <div>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="user-email">{user?.email ?? "none"}</span>
      <button type="button" onClick={() => logout()}>
        Logout
      </button>
      <button type="button" onClick={() => refreshUser()}>
        Refresh
      </button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.clear();
    }
  });

  it("throws when useAuth is used outside AuthProvider", () => {
    expect(() => render(<Consumer />)).toThrow(
      "useAuth must be used within AuthProvider"
    );
  });

  it("starts loading then shows user when token and getMe succeed", async () => {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem("inspectra_token", "t");
    }
    (api.getMe as jest.Mock).mockResolvedValueOnce({
      id: "1",
      email: "a@b.com",
      role: "admin",
      organization_id: "o1",
      first_name: "A",
      last_name: "B",
      status: "active",
    });

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    expect(screen.getByText("Loading")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    });
    expect(screen.getByTestId("user-email")).toHaveTextContent("a@b.com");
  });

  it("starts loading then unauthenticated when no token", async () => {
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    });
    expect(screen.getByTestId("user-email")).toHaveTextContent("none");
  });

  it("sets user null when getMe throws", async () => {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem("inspectra_token", "t");
    }
    (api.getMe as jest.Mock).mockRejectedValueOnce(new Error("Unauthorized"));

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    });
  });

  it("logout calls api logout and clears user", async () => {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem("inspectra_token", "t");
    }
    (api.getMe as jest.Mock).mockResolvedValueOnce({
      id: "1",
      email: "a@b.com",
      role: "admin",
      organization_id: "o1",
      first_name: "A",
      last_name: "B",
      status: "active",
    });

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    });

    await userEvent.click(screen.getByRole("button", { name: "Logout" }));

    expect(api.logout).toHaveBeenCalled();
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
  });

  it("refreshUser refetches and updates user", async () => {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem("inspectra_token", "t");
    }
    (api.getMe as jest.Mock)
      .mockResolvedValueOnce({
        id: "1",
        email: "old@b.com",
        role: "admin",
        organization_id: "o1",
        first_name: "A",
        last_name: "B",
        status: "active",
      })
      .mockResolvedValueOnce({
        id: "1",
        email: "new@b.com",
        role: "admin",
        organization_id: "o1",
        first_name: "A",
        last_name: "B",
        status: "active",
      });

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("old@b.com");
    });

    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("new@b.com");
    });
  });
});
