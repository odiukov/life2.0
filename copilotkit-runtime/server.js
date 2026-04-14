import express from "express";
import cors from "cors";
import { CopilotRuntime, copilotRuntimeNodeHttpEndpoint } from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";

const PORT = 4000;
const ORCHESTRATOR_AGUI_URL =
  process.env.ORCHESTRATOR_AGUI_URL || "http://orchestrator:8000/agui";

const runtime = new CopilotRuntime({
  agents: {
    default: new HttpAgent({ url: ORCHESTRATOR_AGUI_URL }),
  },
});

const app = express();
app.use(cors());

app.get("/health", (_req, res) => res.json({ status: "ok" }));

// Mount at root: the handler's internal Hono app uses basePath "/copilotkit"
// and matches the full request URL, so we must not let Express strip the prefix.
app.use(
  copilotRuntimeNodeHttpEndpoint({
    endpoint: "/copilotkit",
    runtime,
  })
);

app.listen(PORT, () => {
  console.log(`copilotkit-runtime listening on :${PORT}, bridging to ${ORCHESTRATOR_AGUI_URL}`);
});
