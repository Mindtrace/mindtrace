import { render } from "@testing-library/react";
import { useRouter } from "next/navigation";
import Home from "@/app/page";
import { useAuth } from "@/context/auth-context";

jest.mock("next/navigation", () => ({ useRouter: jest.fn() }));
jest.mock("@/context/auth-context", () => ({ useAuth: jest.fn() }));

const mockReplace = jest.fn();
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe("Home Page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({ replace: mockReplace } as ReturnType<
      typeof useRouter
    >);
  });

  it("redirects to /login when not authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    render(<Home />);
    expect(mockReplace).toHaveBeenCalledWith("/login");
  });

  it("redirects to /organizations when super_admin", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "1",
        email: "a@b.com",
        role: "super_admin",
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
    render(<Home />);
    expect(mockReplace).toHaveBeenCalledWith("/organizations");
  });

  it("redirects to /users when not super_admin", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "2",
        email: "c@b.com",
        role: "admin",
        organization_id: "o1",
        first_name: "C",
        last_name: "D",
        status: "active",
      },
      isAuthenticated: true,
      isLoading: false,
      logout: jest.fn(),
      refreshUser: jest.fn(),
    });
    render(<Home />);
    expect(mockReplace).toHaveBeenCalledWith("/users");
  });
});
