import { render, screen } from "@testing-library/react";
import OrganizationsPage from "@/app/(main)/organizations/page";

jest.mock("@/components/organizations/organizations-panel", () => ({
  OrganizationsPanel: () => (
    <div data-testid="organizations-panel">OrganizationsPanel</div>
  ),
}));

describe("Organizations page", () => {
  it("renders heading and OrganizationsPanel", async () => {
    render(<OrganizationsPage />);
    expect(
      screen.getByRole("heading", { name: "Organizations" })
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId("organizations-panel", {}, { timeout: 3000 })
    ).toBeInTheDocument();
  });
});
