import en from '@life-agents/i18n/locales/en.json';
import ru from '@life-agents/i18n/locales/ru.json';
import { appLocale } from '@/lib/locale';
import type { AgentId } from '@life-agents/ui';
import type { TasksApi, TaskSnapshot, TranscriptEntry } from './tasksApi';
import type { TaskEvent } from './taskEvents';

const commandReplies: Record<string, { agent: AgentId; reply: string }> = {
  '/sleep': {
    agent: 'sleep',
    reply: 'Last night: 7h12m · 94% efficiency. HRV avg 62ms (good). Any details to log?',
  },
  '/workout': {
    agent: 'workout',
    reply: "Tell me what you did — type or voice. I'll parse duration / intensity / RPE.",
  },
  '/nutrition': {
    agent: 'nutrition',
    reply: "Describe the meal (e.g., '2 eggs, oats, banana') and I'll log kcal + macros.",
  },
  '/mood': { agent: 'mood', reply: 'How are you feeling 1-10? Anything notable today?' },
  '/journal': { agent: 'mood', reply: "Write freely. I'll extract mood/energy/stress from it." },
  '/habit': { agent: 'habits', reply: "Which habit did you complete? I'll mark it done." },
  '/habits': {
    agent: 'habits',
    reply: 'Today: ☕ coffee-before-noon ✅, 🏃 zone-2 ⬜, 📖 read-30m ⬜ (1/3).',
  },
  '/med': {
    agent: 'medication',
    reply: 'Which medication? Active list: B12 (500μg), Vitamin D (4000IU), Omega-3.',
  },
  '/recovery': {
    agent: 'recovery',
    reply: 'Recovered — HRV +8% vs baseline, RHR −3bpm, stress low, body battery 88%.',
  },
  '/new': { agent: 'home', reply: "New thread started. What's on your mind?" },
  '/finance': {
    agent: 'finance',
    reply: 'This month (USD): $420 food · $180 subs · $90 transport · runway 47d.',
  },
  '/calendar': {
    agent: 'calendar',
    reply: 'Today: 3 meetings, busiest 14-16. First free slot 11:00 for 1h.',
  },
  '/ha': { agent: 'home', reply: 'Living room 21°C · 47% RH · lights off · robot vacuum docked.' },
};

const mockCopy = () => (appLocale() === 'ru' ? ru : en).chat.mock;

const tasks = new Map<string, TaskSnapshot>();
let sequence = 0;
const requireTask = (id: string) => {
  const task = tasks.get(id);
  if (!task) throw new Error('task_not_found');
  return task;
};

export const mockTasksApi: TasksApi = {
  async open(leadAgent = null) {
    const task = { id: `mock-${++sequence}`, leadAgent };
    tasks.set(task.id, { task, messages: [], pendingAction: null });
    return task;
  },
  async read(id) {
    const snapshot = tasks.get(id);
    return snapshot ? (JSON.parse(JSON.stringify(snapshot)) as TaskSnapshot) : null;
  },
  async setLead(id, leadAgent) {
    const snapshot = requireTask(id);
    snapshot.task = { id, leadAgent };
    return snapshot.task;
  },
  async close(id) {
    tasks.delete(id);
  },
  async resolve(id, actionId, decision) {
    const task = requireTask(id);
    const status = decision === 'confirm' ? ('applied' as const) : ('rejected' as const);
    const message = decision === 'confirm' ? mockCopy().applied : mockCopy().rejected;
    if (task.pendingAction?.id !== actionId) throw new Error('already_decided');
    task.messages = task.messages.map((m) =>
      m.role === 'assistant' && m.action?.id === actionId
        ? { ...m, action: { ...m.action, status, message } }
        : m,
    );
    task.pendingAction = null;
    return { status, message };
  },
  post(id, input) {
    let aborted = false;
    async function* events(): AsyncGenerator<TaskEvent> {
      const task = requireTask(id);
      const lead = task.task.leadAgent;
      const canned = Object.values(commandReplies).find((entry) => entry.agent === lead);
      const reply =
        canned?.reply ??
        (/workout|run|train/i.test(input.text)
          ? 'Recovered — HRV +8%, RHR −3. Z2 60min suits today.'
          : 'Recovered. Thanks — logged. You look great today.');
      task.messages.push({
        role: 'user',
        seq: task.messages.length + 1,
        text: input.text,
        attachments: (input.attachments ?? []).map((a) => ({
          kind: a.mime.startsWith('image/') ? 'image' : 'document',
          name: a.name,
          mime: a.mime,
          size: a.size,
        })),
      });
      const assistant: Extract<TranscriptEntry, { role: 'assistant' }> = {
        role: 'assistant',
        seq: task.messages.length + 1,
        text: '',
        agent: lead ?? 'recovery',
        consulted: [],
        action: null,
      };
      yield { type: 'routed', primary: assistant.agent };
      if (/turn off the light|выключи свет/i.test(input.text)) {
        const action = {
          id: `action-${++sequence}`,
          summary: mockCopy().light_summary,
          expiresAt: new Date(Date.now() + 300000).toISOString(),
          status: 'pending' as const,
        };
        assistant.action = action;
        task.pendingAction = action;
        yield { type: 'proposed', action };
      }
      for (const delta of reply.split(/(\s+)/)) {
        if (aborted) return;
        assistant.text += delta;
        yield { type: 'text', delta };
      }
      if (aborted) return;
      task.messages.push(assistant);
      yield { type: 'finished' };
    }
    return {
      events: events(),
      abort() {
        aborted = true;
      },
    };
  },
};
