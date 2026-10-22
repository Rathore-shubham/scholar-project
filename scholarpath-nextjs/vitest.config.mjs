import path from "node:path";
import { fileURLToPath } from "node:url";

import { transformWithOxc } from "vite";
import { defineConfig } from "vitest/config";

const root = path.dirname(fileURLToPath(import.meta.url));

// The app keeps JSX in plain `.js` files (the project is JavaScript-only). Next's compiler accepts that; Vite's
// Oxc transform picks the parser from the file extension, so this test-only plugin compiles `.js` files as JSX.
const jsxInJsFiles = {
  name: "jsx-in-js-files",
  enforce: "pre",
  async transform(code, id) {
    const file = id.split("?")[0];
    if (!file.endsWith(".js") || file.includes("/node_modules/") || file.includes("\\node_modules\\")) return null;
    return transformWithOxc(code, file.replace(/\.js$/, ".jsx"), { jsx: { runtime: "automatic" } });
  },
};

export default defineConfig({
  plugins: [jsxInJsFiles],
  resolve: { alias: { "@": root } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.js"],
    include: ["tests/**/*.test.js"],
    css: false,
  },
});
