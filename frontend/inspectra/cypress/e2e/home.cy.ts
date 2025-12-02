describe("Home Page E2E Tests", () => {
  beforeEach(() => {
    cy.visit("/");
  });

  it("should display the main heading", () => {
    cy.contains("Welcome to Inspectra").should("be.visible");
  });

  it("should display the placeholder description", () => {
    cy.contains("This is a placeholder page for Inspectra skeleton setup").should(
      "be.visible"
    );
  });

  it("should show API connection status", () => {
    cy.contains("API Connection Status").should("be.visible");
    cy.contains("API Response Received", { timeout: 10000 }).should("be.visible");
  });

  it("should display tech stack information", () => {
    cy.contains("Frontend Stack").should("be.visible");
    cy.contains("Next.js").should("be.visible");
    cy.contains("TypeScript").should("be.visible");
    cy.contains("Tailwind CSS").should("be.visible");
  });

  it("should display testing tools information", () => {
    cy.contains("Testing & Quality").should("be.visible");
    cy.contains("React Testing Library").should("be.visible");
    cy.contains("Cypress").should("be.visible");
  });

  it("should have action buttons", () => {
    cy.contains("button", "Get Started").should("be.visible");
    cy.contains("button", "Documentation").should("be.visible");
  });

  it("should be responsive", () => {
    cy.viewport(375, 667); // Mobile viewport
    cy.contains("Welcome to Inspectra").should("be.visible");

    cy.viewport(1280, 720); // Desktop viewport
    cy.contains("Welcome to Inspectra").should("be.visible");
  });
});

