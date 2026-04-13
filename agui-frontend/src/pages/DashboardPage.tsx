import { DashboardPanel } from "../components/DashboardPanel";
import { ChatPanel } from "../components/ChatPanel";
import { useStats } from "../hooks/useStats";

export default function DashboardPage() {
  const { data } = useStats();
  return (
    <div style={{ display: "flex", height: "calc(100vh - 41px)", overflow: "hidden" }}>
      <DashboardPanel stats={data} />
      <ChatPanel />
    </div>
  );
}
