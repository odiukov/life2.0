import { DashboardPanel } from "../components/DashboardPanel";
import { ChatPanel } from "../components/ChatPanel";
import { useHealthSummary } from "../hooks/useHealthSummary";

export default function DashboardPage() {
  const { data } = useHealthSummary();
  return (
    <div style={{ display: "flex", height: "calc(100vh - 41px)", overflow: "hidden" }}>
      <DashboardPanel summary={data} />
      <ChatPanel />
    </div>
  );
}
