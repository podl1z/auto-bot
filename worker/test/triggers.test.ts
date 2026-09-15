import { describe, expect, it } from "vitest";
import { matchesTrigger } from "../src/triggers";
import { renderGreeting, escapeHtml } from "../src/greeting";
import { parseAdminIds } from "../src/index";

const PHRASES = ["старт", "start", "го гулять"];

describe("matchesTrigger", () => {
  it("ловит точное слово", () => {
    expect(matchesTrigger("старт", PHRASES)).toBe(true);
    expect(matchesTrigger("start", PHRASES)).toBe(true);
  });

  it("не зависит от регистра", () => {
    expect(matchesTrigger("СТАРТ", PHRASES)).toBe(true);
    expect(matchesTrigger("Start", PHRASES)).toBe(true);
  });

  it("ловит слово в предложении и с пунктуацией", () => {
    expect(matchesTrigger("ну давай, старт!", PHRASES)).toBe(true);
    expect(matchesTrigger("(старт)", PHRASES)).toBe(true);
  });

  it("не ловит часть слова", () => {
    // Главная защита от того, чтобы бот здоровался на каждое сообщение.
    // В JS это ещё и проверка, что кириллица не сломалась об ASCII-only \b.
    expect(matchesTrigger("стартап", PHRASES)).toBe(false);
    expect(matchesTrigger("рестарт", PHRASES)).toBe(false);
    expect(matchesTrigger("перестартовать", PHRASES)).toBe(false);
    expect(matchesTrigger("restarted", PHRASES)).toBe(false);
  });

  it("ловит фразу из нескольких слов", () => {
    expect(matchesTrigger("ну что, го гулять?", PHRASES)).toBe(true);
    expect(matchesTrigger("го гулятьный", PHRASES)).toBe(false);
  });

  it("переживает пустые входные данные", () => {
    expect(matchesTrigger("", PHRASES)).toBe(false);
    expect(matchesTrigger("старт", [])).toBe(false);
    expect(matchesTrigger("старт", ["", "   "])).toBe(false);
  });

  it("не падает на спецсимволах регулярок", () => {
    expect(matchesTrigger("сколько стоит?", ["стоит?"])).toBe(true);
    expect(matchesTrigger("a+b", ["a+b"])).toBe(true);
  });
});

describe("renderGreeting", () => {
  it("подставляет имя", () => {
    expect(renderGreeting("Привет, {name}!", 1, "Паша")).toBe("Привет, Паша!");
  });

  it("делает кликабельное упоминание", () => {
    expect(renderGreeting("{mention}", 42, "Паша")).toBe(
      '<a href="tg://user?id=42">Паша</a>',
    );
  });

  it("экранирует имя, чтобы не сломать HTML", () => {
    expect(renderGreeting("{name}", 1, "<b>хакер</b>")).toBe(
      "&lt;b&gt;хакер&lt;/b&gt;",
    );
  });

  it("не падает на фигурных скобках в шаблоне", () => {
    expect(renderGreeting("{name} {что-то}", 1, "Паша")).toBe("Паша {что-то}");
  });

  it("подставляет запасное имя, если имени нет", () => {
    expect(renderGreeting("{name}", 1, "")).toBe("друг");
  });
});

describe("escapeHtml", () => {
  it("экранирует амперсанд первым, без двойного экранирования", () => {
    expect(escapeHtml("a & <b>")).toBe("a &amp; &lt;b&gt;");
  });
});

describe("parseAdminIds", () => {
  it("разбирает разные разделители", () => {
    expect([...parseAdminIds("1,2 3;4")]).toEqual([1, 2, 3, 4]);
  });

  it("переживает пустую строку", () => {
    expect(parseAdminIds("").size).toBe(0);
  });
});
