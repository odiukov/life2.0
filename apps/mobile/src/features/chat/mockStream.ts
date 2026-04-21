export type StreamEvent =
  | { type: 'token'; content: string }
  | { type: 'agent'; agent: 'recovery' | 'nutrition' | 'workout' | 'sleep' | 'mood' | 'habits' | 'medication' | 'finance' | 'calendar' | 'home' }
  | { type: 'done' };

type AgentType = 'recovery' | 'nutrition' | 'workout' | 'sleep' | 'mood' | 'habits' | 'medication' | 'finance' | 'calendar' | 'home';

const commandReplies: Record<string, { agent: AgentType; reply: string }> = {
  '/sleep':      { agent: 'sleep',      reply: 'Last night: 7h12m · 94% efficiency. HRV avg 62ms (good). Any details to log?' },
  '/workout':    { agent: 'workout',    reply: "Tell me what you did — type or voice. I'll parse duration / intensity / RPE." },
  '/nutrition':  { agent: 'nutrition',  reply: "Describe the meal (e.g., '2 eggs, oats, banana') and I'll log kcal + macros." },
  '/mood':       { agent: 'mood',       reply: 'How are you feeling 1-10? Anything notable today?' },
  '/journal':    { agent: 'mood',       reply: "Write freely. I'll extract mood/energy/stress from it." },
  '/habit':      { agent: 'habits',     reply: "Which habit did you complete? I'll mark it done." },
  '/habits':     { agent: 'habits',     reply: 'Today: ☕ coffee-before-noon ✅, 🏃 zone-2 ⬜, 📖 read-30m ⬜ (1/3).' },
  '/med':        { agent: 'medication', reply: 'Which medication? Active list: B12 (500μg), Vitamin D (4000IU), Omega-3.' },
  '/recovery':   { agent: 'recovery',   reply: 'Recovered — HRV +8% vs baseline, RHR −3bpm, stress low, body battery 88%.' },
  '/dashboard':  { agent: 'calendar',   reply: '⚡ Recovered · 💤 7h12m · 🔥 1/3 habits · 📅 3 meetings · 💊 B12 −2d · 💰 $4,231' },
  '/new':        { agent: 'home',       reply: "New thread started. What's on your mind?" },
};

export async function* mockAssistantStream(userText: string): AsyncGenerator<StreamEvent> {
  // Slash-command match
  const firstWord = (userText.trim().split(/\s/)[0] ?? '').toLowerCase();
  const cmd = commandReplies[firstWord];
  if (cmd) {
    yield { type: 'agent', agent: cmd.agent };
    await new Promise((r) => setTimeout(r, 150));
    for (const token of cmd.reply.split(/(\s+)/)) {
      await new Promise((r) => setTimeout(r, 30));
      yield { type: 'token', content: token };
    }
    yield { type: 'done' };
    return;
  }
  // Existing free-text fallback
  yield { type: 'agent', agent: 'recovery' };
  await new Promise((r) => setTimeout(r, 200));
  const reply = userText.match(/workout|run|train/i)
    ? 'Recovered — HRV +8%, RHR −3. Z2 60min suits today.'
    : 'Recovered. Thanks — logged. You look great today.';
  for (const token of reply.split(/(\s+)/)) {
    await new Promise((r) => setTimeout(r, 35));
    yield { type: 'token', content: token };
  }
  yield { type: 'done' };
}
