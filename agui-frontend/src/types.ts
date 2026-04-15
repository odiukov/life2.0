export interface AgentStats {
  tasks_week: number;
  tasks_prev_week: number;
  delta: number;
  daily: number[];
}

export interface ActivityItem {
  agent: "sleep" | "workout" | "nutrition";
  task_type: string;
  message: string;
  created_at: string;
}

export interface StatsResponse {
  agents: {
    sleep: AgentStats;
    workout: AgentStats;
    nutrition: AgentStats;
  };
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

export interface AgentInfo {
  name: string;
  url: string;
  online: boolean;
  capabilities: string[];
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
