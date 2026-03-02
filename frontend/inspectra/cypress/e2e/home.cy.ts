describe("Home Page E2E Tests", () => {
  beforeEach(() => {
    cy.visit("/");
  });

  it("redirects unauthenticated users to login", () => {
    cy.url({ timeout: 10000 }).should("include", "/login");
  });

  it("displays the Inspectra heading on login page", () => {
    cy.url({ timeout: 10000 }).should("include", "/login");
    cy.contains("Inspectra").should("be.visible");
  });

  it("displays the sign-in form", () => {
    cy.url({ timeout: 10000 }).should("include", "/login");
    cy.contains("button", "Sign in").should("be.visible");
  });

  it("has email and password inputs", () => {
    cy.url({ timeout: 10000 }).should("include", "/login");
    cy.get('input[type="email"]').should("be.visible");
    cy.get('input[type="password"]').should("be.visible");
  });

  it("is responsive", () => {
    cy.url({ timeout: 10000 }).should("include", "/login");
    cy.viewport(375, 667);
    cy.contains("Inspectra").should("be.visible");
    cy.viewport(1280, 720);
    cy.contains("Inspectra").should("be.visible");
  });
});
