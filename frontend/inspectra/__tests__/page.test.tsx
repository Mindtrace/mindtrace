import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Home from "@/app/page";

// Mock the API client
jest.mock("@/lib/api/client", () => ({
  getHealthCheck: jest.fn(() =>
    Promise.resolve({
      status: "success",
      message: "Mock API response",
      timestamp: "2024-01-01T00:00:00.000Z",
    })
  ),
}));

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

describe("Home Page", () => {
  it("renders the main heading", () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <Home />
      </QueryClientProvider>
    );

    expect(screen.getByText("Welcome to Inspectra")).toBeInTheDocument();
  });

  it("displays the placeholder description", () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <Home />
      </QueryClientProvider>
    );

    expect(
      screen.getByText(/This is a placeholder page for Inspectra/i)
    ).toBeInTheDocument();
  });

  it("shows API connection status after loading", async () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <Home />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("API Response Received")).toBeInTheDocument();
    });

    expect(screen.getByText("Mock API response")).toBeInTheDocument();
  });

  it("displays tech stack badges", () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <Home />
      </QueryClientProvider>
    );

    expect(screen.getByText("Next.js")).toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
    expect(screen.getByText("Tailwind CSS")).toBeInTheDocument();
  });

  it("displays testing tools badges", () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <Home />
      </QueryClientProvider>
    );

    expect(screen.getByText("React Testing Library")).toBeInTheDocument();
    expect(screen.getByText("Cypress")).toBeInTheDocument();
  });
});
