export interface AgentStats {
  tasks_week: number;
  tasks_prev_week: number;
  delta: number;
  daily: number[];
}

export interface ActivityItem {
  agent: string;
  task_type: string;
  message: string;
  created_at: string;
}

export interface StatsResponse {
  agents: Partial<Record<string, AgentStats>>;
  activity: ActivityItem[];
}

export interface BodyMetrics {
  weight_kg?: number;
  body_fat_pct?: number;
  lean_mass_kg?: number;
  bmi?: number;
  recorded_at?: string;
}

export interface SleepSummary {
  duration_hours: number;
  score?: number;
  hrv?: number;
  deep_hours?: number;
  rem_hours?: number;
  light_hours?: number;
  recorded_at?: string;
}

export interface DailyStats {
  steps?: number;
  calories_active?: number;
  body_battery_max?: number;
  resting_hr?: number;
  stress_avg?: number;
  recorded_at?: string;
}

export interface WeeklyTrends {
  sleep_hours: number[];
  workout_minutes: number[];
  nutrition_calories: number[];
}

export interface LastRecommendation {
  agent: string;
  text: string;
  created_at: string;
}

export interface HealthSummary {
  body: BodyMetrics | null;
  sleep: SleepSummary | null;
  daily: DailyStats | null;
  trends: WeeklyTrends;
  recommendation: LastRecommendation | null;
}

export interface AgentSkill {
  id: string;
  name: string;
}

export interface AgentInfo {
  name: string;
  url: string;
  online: boolean;
  skills: AgentSkill[];
  description: string;
  tasks_today: number;
}

export interface AgentsResponse {
  agents: AgentInfo[];
}

export type ToolStatus = "running" | "done" | "error";

export interface ToolCall {
  id: string;
  name: string;
  skill?: string;
  status: ToolStatus;
  startedAt: string;
  endedAt?: string;
  error?: string;
}

export interface LogEntry {
  agent: "sleep" | "workout" | "nutrition";
  skill: string;
  summary: string;
  timestamp: string;
}

export interface HealthAgentState {
  currentStep?: string;
  activeAgent?: "sleep" | "workout" | "nutrition" | null;
  toolCalls?: ToolCall[];
  lastLoggedEntry?: LogEntry | null;
}

export const AGENT_COLORS = {
  sleep:     { emoji: "😴", label: "Sleep",     color: "#4a9eff" },
  workout:   { emoji: "💪", label: "Workout",   color: "#4eff9a" },
  nutrition: { emoji: "🥗", label: "Nutrition", color: "#ffb74a" },
  body:       { emoji: "🦍", label: "Body",       color: "#c691ff" },
  mood:       { emoji: "🙂", label: "Mood",       color: "#ff91b5" },
  habits:     { emoji: "✅", label: "Habits",     color: "#91d8ff" },
  recovery:   { emoji: "🌿", label: "Recovery",   color: "#7effb5" },
  medication: { emoji: "💊", label: "Medication", color: "#ff9a9a" },
} as const;

export type AgentKey = keyof typeof AGENT_COLORS;

export type Selection =
  | { kind: "agent"; name: AgentKey }
  | { kind: "orchestrator" }
  | { kind: "tool"; name: string }
  | { kind: "data"; name: string }
  | null;

export interface ToolNode {
  name: string;
  port: string;
  description: string;
}

export const TOOL_NODES: ToolNode[] = [
  { name: "calendar-mcp", port: ":9100", description: "MCP server exposing calendar read/write tools." },
  { name: "home-assistant", port: "lan:8123", description: "HA native MCP server — live state (GetLiveContext) + confirm-gated Hass* mutations." },
];

export interface DataNode {
  name: string;
  port: string;
  description: string;
}

export const DATA_NODES: DataNode[] = [
  {
    name: "finance",
    port: "sql",
    description: "Finance data in Postgres (finance_transactions). Currently ingests Payoneer PDF statements only; more sources can be added later. Tools: query_finance_summary / categories / runway.",
  },
];

export function peersOf(
  selected: Selection,
  agents: AgentInfo[],
  tools: ToolNode[],
  data: DataNode[] = DATA_NODES,
): Set<string> {
  const peers = new Set<string>();
  if (!selected) return peers;
  if (selected.kind === "orchestrator") {
    peers.add("user");
    for (const a of agents) peers.add(`agent:${a.name}`);
    for (const t of tools) peers.add(`tool:${t.name}`);
    for (const d of data) peers.add(`data:${d.name}`);
  } else if (selected.kind === "agent") {
    peers.add("orchestrator");
    for (const a of agents) {
      if (a.name !== selected.name) peers.add(`agent:${a.name}`);
    }
  } else if (selected.kind === "tool") {
    peers.add("orchestrator");
  } else if (selected.kind === "data") {
    peers.add("orchestrator");
  }
  return peers;
}
