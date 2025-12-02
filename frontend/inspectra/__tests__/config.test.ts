/**
 * Configuration tests to ensure all configs are properly set up
 */

describe("Configuration Tests", () => {
  describe("Environment", () => {
    it("should have test environment configured", () => {
      expect(process.env.NODE_ENV).toBeDefined();
    });
  });

  describe("TypeScript", () => {
    it("should compile TypeScript files", () => {
      // This test ensures TypeScript compilation works
      const testValue: string = "test";
      expect(typeof testValue).toBe("string");
    });
  });

  describe("Zod", () => {
    it("should validate data with Zod", async () => {
      const { z } = await import("zod");
      const schema = z.object({
        name: z.string(),
        age: z.number(),
      });

      const validData = { name: "Test", age: 25 };
      const result = schema.parse(validData);

      expect(result).toEqual(validData);
    });

    it("should throw error on invalid Zod data", async () => {
      const { z } = await import("zod");
      const schema = z.object({
        name: z.string(),
        age: z.number(),
      });

      const invalidData = { name: "Test", age: "not a number" as unknown as number };

      expect(() => schema.parse(invalidData)).toThrow();
    });
  });

  describe("Utils", () => {
    it("should merge class names correctly", async () => {
      const { cn } = await import("@/lib/utils");
      const result = cn("class1", "class2");
      expect(typeof result).toBe("string");
      expect(result).toContain("class1");
      expect(result).toContain("class2");
    });
  });
});
