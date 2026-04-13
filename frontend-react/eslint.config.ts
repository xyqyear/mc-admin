import js from "@eslint/js";
import pluginReact from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["dist/**"]),

  {
    files: ["**/*.{js,mjs,cjs,jsx,ts,mts,cts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },

  {
    files: ["**/*.{jsx,tsx}"],
    extends: [
      pluginReact.configs.flat.recommended,
      pluginReact.configs.flat["jsx-runtime"],
    ],
    settings: { react: { version: "detect" } },
  },

  reactHooks.configs["recommended-latest"],
  reactRefresh.configs.vite,

  // shadcn UI boilerplate co-locates variant constants (cva) and context
  // with components, which trips react-refresh/only-export-components.
  // Fast refresh still works for consumer code; these files are edited rarely.
  {
    files: [
      "src/components/ui/**/*.{ts,tsx}",
      "src/components/theme-provider.tsx",
    ],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },

  {
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
  },
]);
