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
