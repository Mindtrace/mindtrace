import { render, screen } from "@testing-library/react";
import { useRouter } from "next/navigation";
import MainLayout from "@/app/(main)/layout";
import { useAuth } from "@/context/auth-context";

jest.mock("next/navigation", () => ({ useRouter: jest.fn() }));
jest.mock("@/context/auth-context", () => ({ useAuth: jest.fn() }));
jest.mock("@/components/layout/app-sidebar", () => ({
  AppSidebar: () => <div data-testid="app-sidebar">Sidebar</div>,
}));
jest.mock("@/components/ui/loading-overlay", () => ({
  LoadingOverlay: () => <div data-testid="loading">Loading</div>,
}));
jest.mock("@/components/ui/sidebar", () => ({
  SidebarProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="sidebar-provider">{children}</div>
  ),
  SidebarInset: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="sidebar-inset">{children}</div>
  ),
}));

const mockReplace = jest.fn();
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe("Main layout", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      replace: mockReplace,
    } as unknown as ReturnType<typeof useRouter>);
  });

  it("shows LoadingOverlay when isLoading", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: true,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    render(
      <MainLayout>
        <span>Child</span>
      </MainLayout>
    );
    expect(screen.getByTestId("loading")).toBeInTheDocument();
  });

  it("redirects to /login when not authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    render(
      <MainLayout>
        <span>Child</span>
      </MainLayout>
    );
    expect(mockReplace).toHaveBeenCalledWith("/login");
  });

  it("returns null when not authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    const { container } = render(
      <MainLayout>
        <span>Child</span>
      </MainLayout>
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders sidebar and children when authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "1",
        email: "a@b.com",
        role: "admin",
        organization_id: "o1",
        first_name: "A",
        last_name: "B",
        status: "active",
      },
      isAuthenticated: true,
      isLoading: false,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    render(
      <MainLayout>
        <span>Child</span>
      </MainLayout>
    );
    expect(screen.getByTestId("app-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-provider")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-inset")).toBeInTheDocument();
    expect(screen.getByText("Child")).toBeInTheDocument();
  });
});
