import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-plugin-prettier";
import prettierConfig from "eslint-config-prettier";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  prettierConfig,
  {
    plugins: {
      prettier,
    },
    rules: {
      "prettier/prettier": "error",
      // Airbnb-style rules
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-debugger": "error",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
        },
      ],
      "import/prefer-default-export": "off",
      // Allow function declarations for Next.js pages and layouts
      "react/function-component-definition": "off",
      "react/jsx-props-no-spreading": "off",
      "react/require-default-props": "off",
      "@typescript-eslint/explicit-function-return-type": "off",
      "@typescript-eslint/explicit-module-boundary-types": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "node_modules/**",
    "coverage/**",
    ".cypress/**",
    "cypress/videos/**",
    "cypress/screenshots/**",
    "jest.config.js", // Jest config uses require()
  ]),
]);

export default eslintConfig;
