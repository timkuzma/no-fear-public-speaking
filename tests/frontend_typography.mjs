import assert from "node:assert/strict";
import { bindShortWords } from "../public/typography.js";

assert.equal(bindShortWords("Подготовься к своему выступлению"), "Подготовься к\u00a0своему выступлению");
assert.equal(bindShortWords("Запиши речь и получи разбор"), "Запиши речь и\u00a0получи разбор");
assert.equal(bindShortWords("И в той же тренировке"), "И\u00a0в\u00a0той же\u00a0тренировке");
assert.equal(bindShortWords("До 1 минуты, без камеры"), "До\u00a01 минуты, без\u00a0камеры");
assert.equal(bindShortWords("Ответь на «вопрос»"), "Ответь на\u00a0«вопрос»");
assert.equal(bindShortWords("слова: но\nэто новая строка"), "слова: но\nэто\u00a0новая строка");
assert.equal(bindShortWords("темы, слова и"), "темы, слова и");
assert.equal(bindShortWords("сцена, окно, кино, правило"), "сцена, окно, кино, правило");
assert.equal(bindShortWords("Ни, не. Но!"), "Ни, не. Но!");
assert.equal(bindShortWords("https://example.test/api?id=1"), "https://example.test/api?id=1");
const once = bindShortWords("В той же речи и в разборе");
assert.equal(bindShortWords(once), once);
console.log("Russian typography boundary cases passed");
