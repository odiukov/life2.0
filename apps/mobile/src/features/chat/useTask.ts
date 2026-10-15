import { useCallback, useRef, useState } from 'react';
import type { AgentId } from '@life-agents/ui';
import { clearOpenTaskId, loadOpenTaskId, saveOpenTaskId } from './taskStorage';
import {
  defaultTasksApi,
  TaskBusyError,
  TasksApiError,
  type AttachmentMeta,
  type OutgoingAttachment,
  type TaskSnapshot,
  type TasksApi,
} from './tasksApi';
import type { MessageStream } from './sse';
import type { ActionState, ActionStatus } from './taskEvents';

export type { ActionState, ActionStatus, OutgoingAttachment };
export type Phase = 'idle' | 'restoring' | 'sending' | 'streaming';
export type ChatMessage =
  | { kind: 'user'; id: string; text: string; tag?: AgentId; attachments: AttachmentMeta[] }
  | {
      kind: 'assistant';
      id: string;
      text: string;
      agent?: AgentId;
      consulted?: AgentId[];
      streaming: boolean;
      action?: ActionState;
    }
  | { kind: 'error'; id: string; code: string; message: string };
export type SendInput = { text: string; tag?: AgentId; attachments?: OutgoingAttachment[] };

const BUSY_RETRIES = 3;
const BUSY_DELAY_MS = 500;
let seq = 0;
const localId = (p: string) => `${p}${Date.now()}-${seq++}`;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function fromSnapshot(s: TaskSnapshot): ChatMessage[] {
  return s.messages.map((m) =>
    m.role === 'user'
      ? { kind: 'user', id: `s${m.seq}`, text: m.text, attachments: m.attachments }
      : {
          kind: 'assistant',
          id: `s${m.seq}`,
          text: m.text,
          agent: m.agent ?? undefined,
          consulted: m.consulted,
          streaming: false,
          action: m.action ?? undefined,
        },
  );
}

export function useTask(api: TasksApi = defaultTasksApi()) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [leadAgent, setLeadAgent] = useState<AgentId | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingAction, setPendingAction] = useState<ActionState | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [interrupted, setInterrupted] = useState(false);
  const task = useRef<{ id: string | null; lead: AgentId | null }>({ id: null, lead: null });
  const stream = useRef<MessageStream | null>(null);
  const resolving = useRef(new Set<string>());
  const busy = useRef(false);
  const closing = useRef(false);
  const unreadTask = useRef<string | null>(null);
  const generation = useRef(0);
  const operations = useRef<Promise<void>>(Promise.resolve());
  const serialize = useCallback(<T>(operation: () => Promise<T>): Promise<T> => {
    const result = operations.current.then(operation);
    operations.current = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }, []);

  const reset = useCallback(() => {
    task.current = { id: null, lead: null };
    setTaskId(null);
    setLeadAgent(null);
    setMessages([]);
    setPendingAction(null);
    setInterrupted(false);
  }, []);

  const setActionStatus = useCallback(
    (actionId: string, status: ActionStatus, message?: string) => {
      setMessages((all) =>
        all.map((m) =>
          m.kind === 'assistant' && m.action?.id === actionId
            ? { ...m, action: { ...m.action, status, message } }
            : m,
        ),
      );
      setPendingAction((p) => (p?.id === actionId && status !== 'pending' ? null : p));
    },
    [],
  );

  const readSavedTask = useCallback(async () => {
    const id = unreadTask.current ?? (await loadOpenTaskId());
    if (!id) return;
    unreadTask.current = id;
    const snapshot = await api.read(id);
    if (!snapshot) {
      await clearOpenTaskId();
      unreadTask.current = null;
      reset();
      return;
    }
    task.current = { id: snapshot.task.id, lead: snapshot.task.leadAgent };
    setTaskId(snapshot.task.id);
    setLeadAgent(snapshot.task.leadAgent);
    setMessages(fromSnapshot(snapshot));
    setPendingAction(snapshot.pendingAction);
    setInterrupted(snapshot.messages.at(-1)?.role === 'user');
    unreadTask.current = null;
  }, [api, reset]);

  const restore = useCallback(async () => {
    if (busy.current || closing.current) return;
    busy.current = true;
    setPhase('restoring');
    try {
      await serialize(readSavedTask);
    } finally {
      busy.current = false;
      setPhase('idle');
    }
  }, [readSavedTask, serialize]);

  // Only identity operations in the queue call this helper.
  const ensureTask = useCallback(
    async (lead: AgentId | null | undefined): Promise<string> => {
      if (unreadTask.current) await readSavedTask();
      if (!task.current.id) {
        const opened = await api.open(lead ?? null);
        task.current = { id: opened.id, lead: opened.leadAgent };
        setTaskId(opened.id);
        setLeadAgent(opened.leadAgent);
        await saveOpenTaskId(opened.id);
      } else if (lead !== undefined && lead !== task.current.lead) {
        const updated = await api.setLead(task.current.id, lead);
        task.current = { id: updated.id, lead: updated.leadAgent };
        setLeadAgent(updated.leadAgent);
      }
      return task.current.id!;
    },
    [api, readSavedTask],
  );

  const setLead = useCallback(
    async (lead: AgentId | null) => {
      if (closing.current) throw new TaskBusyError('task_busy');
      const version = generation.current;
      await serialize(async () => {
        if (version !== generation.current) return;
        await ensureTask(lead);
      });
    },
    [ensureTask, serialize],
  );

  const send = useCallback(
    async ({ text, tag, attachments = [] }: SendInput) => {
      if (closing.current || busy.current || (!text.trim() && attachments.length === 0))
        return false;
      const version = generation.current;
      let completed = false;
      let failed = false;
      busy.current = true;
      setPhase('sending');
      setInterrupted(false);
      const aid = localId('a');
      const patch = (
        fn: (
          m: Extract<ChatMessage, { kind: 'assistant' }>,
        ) => Partial<Extract<ChatMessage, { kind: 'assistant' }>>,
      ) =>
        setMessages((all) =>
          all.map((m) => (m.id === aid && m.kind === 'assistant' ? { ...m, ...fn(m) } : m)),
        );
      const error = (code: string, message: string) =>
        setMessages((all) => [...all, { kind: 'error', id: localId('e'), code, message }]);
      try {
        const id = await serialize(async () => {
          if (version !== generation.current) return null;
          return ensureTask(tag);
        });
        if (!id || closing.current || version !== generation.current) return false;
        setMessages((m) => [
          ...m,
          {
            kind: 'user',
            id: localId('u'),
            text,
            tag,
            attachments: attachments.map((a) => ({
              kind: a.mime.startsWith('image/') ? 'image' : 'document',
              name: a.name,
              mime: a.mime,
              size: a.size,
            })),
          },
          { kind: 'assistant', id: aid, text: '', streaming: true },
        ]);
        setInterrupted(false);
        const s = api.post(id, { text, attachments });
        stream.current = s;
        setPhase('streaming');
        for await (const ev of s.events) {
          if (version !== generation.current) break;
          switch (ev.type) {
            case 'text':
              patch((m) => ({ text: m.text + ev.delta }));
              break;
            case 'routed':
              patch(() => ({ agent: ev.primary ?? undefined }));
              break;
            case 'consulted':
              patch(() => ({ consulted: ev.peers }));
              break;
            case 'proposed':
              setMessages((all) =>
                all.map((m) =>
                  m.kind === 'assistant' &&
                  m.action?.status === 'pending' &&
                  m.action.id !== ev.action.id
                    ? { ...m, action: { ...m.action, status: 'expired' } }
                    : m,
                ),
              );
              patch(() => ({ action: ev.action }));
              setPendingAction(ev.action);
              break;
            case 'resolved':
              setActionStatus(ev.actionId, ev.status, ev.message);
              break;
            case 'error':
              failed = true;
              error(ev.code, ev.message);
              break;
            case 'http_error':
              failed = true;
              error(ev.code, '');
              break;
            case 'finished':
              completed = true;
              break;
          }
        }
      } catch (e) {
        failed = true;
        if (version !== generation.current) return false;
        error(
          e instanceof TaskBusyError
            ? 'task_busy'
            : e instanceof TasksApiError
              ? e.code
              : 'network',
          '',
        );
      } finally {
        stream.current = null;
        patch(() => ({ streaming: false }));
        setMessages((all) =>
          all.filter((m) => !(m.id === aid && m.kind === 'assistant' && !m.text && !m.action)),
        );
        busy.current = false;
        setPhase('idle');
      }
      return completed && !failed && version === generation.current;
    },
    [api, ensureTask, setActionStatus, serialize],
  );

  const decide = useCallback(
    async (actionId: string, decision: 'confirm' | 'reject') => {
      const id = task.current.id;
      if (!id || closing.current || resolving.current.has(actionId)) return;
      const version = generation.current;
      resolving.current.add(actionId);
      try {
        const result = await api.resolve(id, actionId, decision);
        if (version === generation.current)
          setActionStatus(actionId, result.status, result.message);
      } catch (e) {
        if (e instanceof TaskBusyError || version !== generation.current) return;
        // A lost response says nothing about whether the server applied the action.
        setMessages((all) => [
          ...all,
          { kind: 'error', id: localId('e'), code: 'network', message: '' },
        ]);
      } finally {
        resolving.current.delete(actionId);
      }
    },
    [api, setActionStatus],
  );

  const close = useCallback(async () => {
    if (closing.current) throw new TaskBusyError('task_busy');
    closing.current = true;
    generation.current += 1;
    try {
      stream.current?.abort();
      await serialize(async () => {
        const id = task.current.id ?? unreadTask.current;
        if (id) {
          for (let attempt = 1; ; attempt++) {
            try {
              await api.close(id);
              break;
            } catch (e) {
              if (!(e instanceof TaskBusyError) || attempt >= BUSY_RETRIES) throw e;
              await sleep(BUSY_DELAY_MS);
            }
          }
        }
        await clearOpenTaskId();
        unreadTask.current = null;
        reset();
      });
    } finally {
      closing.current = false;
    }
  }, [api, reset, serialize]);

  return {
    taskId,
    leadAgent,
    messages,
    pendingAction,
    phase,
    interrupted,
    restore,
    send,
    setLead,
    close,
    startNew: close,
    confirm: (actionId: string) => decide(actionId, 'confirm'),
    reject: (actionId: string) => decide(actionId, 'reject'),
  };
}
