import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCopilotAction } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { DashboardPanel } from "../components/DashboardPanel";
import { useHealthSummary } from "../hooks/useHealthSummary";

export default function DashboardPage() {
  const { data, refresh } = useHealthSummary();
  const navigate = useNavigate();
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);

  useCopilotAction({
    name: "refresh_health_data",
    description: "Refresh the health metrics displayed on the dashboard",
    parameters: [],
    handler: () => {
      refresh();
    },
  });

  useCopilotAction({
    name: "navigate_to_agents",
    description: "Switch to the Agents tab to show agent topology and stats",
    parameters: [],
    handler: () => {
      navigate("/agents");
    },
  });

  useCopilotAction({
    name: "highlight_agent",
    description: "Navigate to the Agents tab and visually highlight a specific agent",
    parameters: [
      {
        name: "agent",
        type: "string",
        description: "Which agent to highlight: sleep | workout | nutrition",
      },
    ],
    handler: ({ agent }: { agent: string }) => {
      navigate("/agents", { state: { highlighted: agent } });
    },
  });

  useCopilotAction({
    name: "show_metric_detail",
    description: "Visually highlight a specific health metric card on the dashboard",
    parameters: [
      {
        name: "metric",
        type: "string",
        description: "Which metric to highlight: sleep | weight | steps | body_battery",
      },
    ],
    handler: ({ metric }: { metric: string }) => {
      setExpandedMetric(metric);
      setTimeout(() => setExpandedMetric(null), 4000);
    },
  });

  return (
    <div style={{ display: "flex", height: "calc(100vh - 41px)", overflow: "hidden" }}>
      <DashboardPanel summary={data} expandedMetric={expandedMetric} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <CopilotChat
          instructions={
            "You are a personal health assistant. The user tracks sleep, workouts, and nutrition. " +
            "Use call_health_agent to fetch analysis from specialist agents before responding. " +
            "Use run_sync when the user wants to synchronize data. " +
            "Use run_briefing to generate and send the daily health briefing. " +
            "Use refresh_health_data after a sync to update the dashboard. " +
            "Use highlight_agent to draw the user's attention to a specific agent. " +
            "Use show_metric_detail to highlight a specific metric card."
          }
          labels={{
            title: "life-agents",
            initial: "Ask about your sleep, workouts, or nutrition.",
          }}
        />
      </div>
    </div>
  );
}
