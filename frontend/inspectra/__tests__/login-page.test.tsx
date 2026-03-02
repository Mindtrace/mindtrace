import { render, screen } from "@testing-library/react";
import { useRouter } from "next/navigation";
import LoginPage from "@/app/login/page";
import { useAuth } from "@/context/auth-context";

jest.mock("next/navigation", () => ({ useRouter: jest.fn() }));
jest.mock("@/context/auth-context", () => ({ useAuth: jest.fn() }));

const mockReplace = jest.fn();
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe("Login page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      replace: mockReplace,
    } as unknown as ReturnType<typeof useRouter>);
  });

  it("shows loading spinner when isLoading", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: true,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    render(<LoginPage />);
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("renders LoginForm when not loading and not authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    render(<LoginPage />);
    expect(
      screen.getByRole("heading", { name: "Inspectra" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("redirects to / when already authenticated", () => {
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
    render(<LoginPage />);
    expect(mockReplace).toHaveBeenCalledWith("/");
  });

  it("returns null when authenticated", () => {
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
    const { container } = render(<LoginPage />);
    expect(container.firstChild).toBeNull();
  });
});
