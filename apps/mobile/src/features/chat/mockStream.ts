export type StreamEvent =
  | { type: 'token'; content: string }
  | { type: 'agent'; agent: 'recovery' | 'nutrition' | 'workout' | 'sleep' | 'mood' | 'habits' | 'medication' | 'finance' | 'calendar' | 'home' }
  | { type: 'done' };

export async function* mockAssistantStream(userText: string): AsyncGenerator<StreamEvent> {
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
