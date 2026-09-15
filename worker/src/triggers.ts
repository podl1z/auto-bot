/** Матчинг слов-триггеров. Порт bot/filters.py:matches_trigger. */

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// В JavaScript \b и \w — только ASCII, поэтому «старт» в «стартап» считался бы
// отдельным словом. Берём границы через свойства Unicode: буква, цифра или _.
const WORD_CHAR = "[\\p{L}\\p{N}_]";

/**
 * Ищет фразу в тексте по границам слова.
 *
 * «старт» ловится в «старт» и «Старт!», но не в «стартап» и не в «рестарт» —
 * иначе в группе бот здоровался бы на каждое второе сообщение.
 */
export function matchesTrigger(text: string, phrases: string[]): boolean {
  if (!text || phrases.length === 0) return false;
  for (const raw of phrases) {
    const phrase = raw.trim().toLowerCase();
    if (!phrase) continue;
    const re = new RegExp(
      `(?<!${WORD_CHAR})${escapeRegExp(phrase)}(?!${WORD_CHAR})`,
      "iu",
    );
    if (re.test(text)) return true;
  }
  return false;
}
