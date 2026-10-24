// Lakelink Fiber — Provable Resilience Intelligence frontend lint config (P27-APP-COMMIT-FE-MANIFEST).
// ESLint 9 flat config. CI runs: npx --no-install eslint "src/**/*.{ts,tsx}" --max-warnings 0
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default tseslint.config(
  {
    // Generated or built output: never lint
    ignores: [
      "src/resilience_scorecard/__dist__/**",
      "src/resilience_scorecard/ui/routeTree.gen.ts",
      "node_modules/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "module",
      globals: { ...globals.browser },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
    },
  },
);
