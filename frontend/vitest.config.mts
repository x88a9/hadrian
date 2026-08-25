import { defineConfig } from "vitest/config";

// Minimal config: we only unit-test pure functions in lib/*.ts (no DOM, no
// component rendering), so plain node is enough and there is no need for a
// jsdom dependency or path-alias resolution (test files import their
// subjects with relative paths).
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
