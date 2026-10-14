const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const LOOKALIKE: Record<string, string> = { O: '0', I: '1', L: '1' };

/** Normalize invite input with the same alphabet as the household service. */
export function formatInviteInput(raw: string): string {
  const chars = [...raw.toUpperCase()]
    .map((character) => LOOKALIKE[character] ?? character)
    .filter((character) => ALPHABET.includes(character))
    .slice(0, 8)
    .join('');
  return chars.length > 4 ? `${chars.slice(0, 4)}-${chars.slice(4)}` : chars;
}
