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

app.use("/copilotkit", (req, res, next) =>
  copilotRuntimeNodeHttpEndpoint({
    endpoint: "/copilotkit",
    runtime,
  })(req, res, next)
);

app.listen(PORT, () => {
  console.log(`copilotkit-runtime listening on :${PORT}, bridging to ${ORCHESTRATOR_AGUI_URL}`);
});
