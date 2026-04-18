// Patch upstream google-calendar-mcp v2.6.1 so it works with
// langchain-mcp-adapters' persistent-session usage pattern in the orchestrator:
//
//   - stateful sessions (UUIDs) instead of the default stateless mode, which in
//     this SDK version returns 500 on the second request of a session
//   - JSON responses instead of SSE streaming; keeps latency low and the
//     Python client happy for a single long-lived session

const fs = require("fs");

const bundlePath = "/app/build/index.js";
let bundle = fs.readFileSync(bundlePath, "utf8");
const before =
  'sessionIdGenerator: void 0\n      // Stateless mode - allows multiple initializations\n    });';
const after =
  "sessionIdGenerator: () => crypto.randomUUID(),\n      enableJsonResponse: true\n    });";
if (!bundle.includes(before)) {
  throw new Error("life-agents patch: bundle pattern not found — upstream changed?");
}
fs.writeFileSync(bundlePath, bundle.replace(before, after));
console.log("life-agents patch: bundle patched (stateful + JSON response)");
