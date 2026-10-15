import type { AgentId } from '@life-agents/ui';
import { apiBaseUrl, apiMode } from '@/api/client';
import { errorCode, gateway } from '@/api/gateway';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';
import { mockTasksApi } from './mockTasksApi';
import { postSse, type MessageStream } from './sse';
import type { ActionState, ActionStatus } from './taskEvents';
import { isAgentId } from '../agents/agentStatusRules';

export type TaskInfo = { id: string; leadAgent: AgentId | null };
export type AttachmentMeta = {
  kind: 'image' | 'document';
  name: string;
  mime: string;
  size: number;
};
export type TranscriptEntry =
  | { role: 'user'; seq: number; text: string; attachments: AttachmentMeta[] }
  | {
      role: 'assistant';
      seq: number;
      text: string;
      agent: AgentId | null;
      consulted: AgentId[];
      action: ActionState | null;
    };
export type TaskSnapshot = {
  task: TaskInfo;
  messages: TranscriptEntry[];
  pendingAction: ActionState | null;
};
export type OutgoingAttachment = { uri: string; name: string; mime: string; size: number };
export type OutgoingMessage = { text: string; attachments?: OutgoingAttachment[] };

export class TaskBusyError extends Error {}
export class TasksApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
  ) {
    super(code);
  }
}

export interface TasksApi {
  open(lead?: AgentId | null): Promise<TaskInfo>;
  read(id: string): Promise<TaskSnapshot | null>;
  setLead(id: string, lead: AgentId | null): Promise<TaskInfo>;
  close(id: string): Promise<void>;
  resolve(
    taskId: string,
    actionId: string,
    decision: 'confirm' | 'reject',
  ): Promise<{ status: ActionStatus; message: string }>;
  post(id: string, input: OutgoingMessage): MessageStream;
}

const lead = (v: unknown): AgentId | null => (isAgentId(v) ? v : null);
const fail = (error: unknown, response: Response | undefined): never => {
  const code = errorCode(error) ?? 'http';
  if (code === 'task_busy') throw new TaskBusyError(code);
  throw new TasksApiError(code, response?.status ?? 0);
};

export const realTasksApi: TasksApi = {
  async open(leadAgent) {
    const { data, error, response } = await gateway.POST('/tasks', {
      body: { lead_agent: leadAgent ?? null },
    });
    if (error || !data) return fail(error, response);
    return { id: data.id, leadAgent: lead(data.lead_agent) };
  },
  async read(id) {
    const { data, error, response } = await gateway.GET('/tasks/{task_id}', {
      params: { path: { task_id: id } },
    });
    if (response?.status === 404) return null;
    if (error || !data) return fail(error, response);
    const pending = data.pending_action;
    return {
      task: { id: data.task.id, leadAgent: lead(data.task.lead_agent) },
      pendingAction: pending
        ? {
            id: pending.id,
            summary: pending.summary,
            expiresAt: pending.expires_at,
            status: 'pending',
          }
        : null,
      messages: data.messages.map((m) =>
        m.role === 'user'
          ? {
              role: 'user',
              seq: m.seq,
              text: m.text,
              attachments: m.attachments as AttachmentMeta[],
            }
          : {
              role: 'assistant',
              seq: m.seq,
              text: m.text,
              agent: lead(m.agent),
              consulted: m.consulted.filter(isAgentId),
              action: m.action
                ? {
                    id: String(m.action.id),
                    summary: String(m.action.summary),
                    status: m.action.status as ActionStatus,
                    expiresAt: pending && pending.id === m.action.id ? pending.expires_at : null,
                  }
                : null,
            },
      ),
    };
  },
  async setLead(id, leadAgent) {
    const { data, error, response } = await gateway.PATCH('/tasks/{task_id}', {
      params: { path: { task_id: id } },
      body: { lead_agent: leadAgent },
    });
    if (error || !data) return fail(error, response);
    return { id: data.id, leadAgent: lead(data.lead_agent) };
  },
  async close(id) {
    const { error, response } = await gateway.DELETE('/tasks/{task_id}', {
      params: { path: { task_id: id } },
    });
    if (response?.status === 404) return; // already gone counts as closed
    if (error) fail(error, response);
  },
  async resolve(taskId, actionId, decision) {
    const { data, error, response } = await gateway.POST('/tasks/{task_id}/actions/{action_id}', {
      params: { path: { task_id: taskId, action_id: actionId } },
      body: { decision },
    });
    if (error || !data) return fail(error, response);
    return { status: data.status as ActionStatus, message: data.message };
  },
  post(id, input) {
    const form = new FormData();
    form.append('text', input.text);
    form.append('timezone', Intl.DateTimeFormat().resolvedOptions().timeZone);
    for (const a of input.attachments ?? [])
      form.append('attachments', { uri: a.uri, name: a.name, type: a.mime } as unknown as Blob);
    let inner: MessageStream | null = null;
    let aborted = false;
    async function* events() {
      const headers = await getAuthHeaders();
      if (aborted) return;
      inner = postSse(`${apiBaseUrl}/tasks/${encodeURIComponent(id)}/messages`, headers, form);
      yield* inner.events;
    }
    return {
      events: events(),
      abort: () => {
        aborted = true;
        inner?.abort();
      },
    };
  },
};

export function defaultTasksApi(): TasksApi {
  return apiMode === 'mock' ? mockTasksApi : realTasksApi;
}
