import { render, screen } from "@testing-library/react";
import UsersPage from "@/app/(main)/users/page";

jest.mock("@/components/users/users-panel", () => ({
  UsersPanel: () => <div data-testid="users-panel">UsersPanel</div>,
}));

describe("Users page", () => {
  it("renders heading and UsersPanel", async () => {
    render(<UsersPage />);
    expect(screen.getByRole("heading", { name: "Users" })).toBeInTheDocument();
    expect(
      await screen.findByTestId("users-panel", {}, { timeout: 3000 })
    ).toBeInTheDocument();
  });
});
