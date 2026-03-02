import { render, screen } from "@testing-library/react";
import { QueryProvider } from "@/components/providers/query-provider";

describe("QueryProvider", () => {
  it("renders children", () => {
    render(
      <QueryProvider>
        <span>Child</span>
      </QueryProvider>
    );
    expect(screen.getByText("Child")).toBeInTheDocument();
  });
});
