import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "@/components/auth/login-form";
import * as api from "@/lib/api/client";

jest.mock("@/lib/api/client", () => ({ login: jest.fn() }));

describe("LoginForm", () => {
  const onSuccess = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders sign in title and fields", () => {
    render(<LoginForm onSuccess={onSuccess} />);
    expect(screen.getByText("Use your Inspectra account.")).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("calls onSuccess after successful login", async () => {
    (api.login as jest.Mock).mockResolvedValueOnce({
      access_token: "t",
      token_type: "bearer",
      refresh_token: "r",
    });

    render(<LoginForm onSuccess={onSuccess} />);
    await userEvent.type(screen.getByLabelText(/email/i), "u@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(api.login).toHaveBeenCalledWith("u@example.com", "pass");
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });

  it("shows error when email and password are empty", async () => {
    render(<LoginForm onSuccess={onSuccess} />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Email and password are required"
    );
    expect(api.login).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("shows error with reference code when login fails", async () => {
    (api.login as jest.Mock).mockRejectedValueOnce(
      new Error("Invalid credentials")
    );

    render(<LoginForm onSuccess={onSuccess} />);
    await userEvent.type(screen.getByLabelText(/email/i), "u@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("Login failed");
    expect(screen.getByRole("alert")).toHaveTextContent("reference code");
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
