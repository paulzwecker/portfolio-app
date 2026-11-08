import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync("src/app/globals.css", "utf8");
function block(selector: string) {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`Missing ${selector}`);
  return css.slice(start, css.indexOf("}", start));
}
function token(source: string, name: string) {
  const value = source.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6});`, "i"));
  if (!value) throw new Error(`Missing color ${name}`);
  return value[1];
}
function luminance(hex: string) {
  const rgb = hex
    .slice(1)
    .match(/../g)!
    .map((part) => parseInt(part, 16) / 255);
  return rgb
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce(
      (total, value, index) => total + value * [0.2126, 0.7152, 0.0722][index],
      0,
    );
}
function contrast(a: string, b: string) {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("shared palette", () => {
  for (const [theme, selector] of [
    ["light", ":root"],
    ["dark", ':root[data-theme="dark"]'],
  ]) {
    it(`${theme} text and action pairs meet normal-text contrast`, () => {
      const source = block(selector);
      for (const [foreground, background] of [
        ["foreground", "background"],
        ["card-foreground", "card"],
        ["muted-foreground", "card"],
        ["primary-foreground", "primary"],
        ["info", "card"],
        ["positive", "card"],
        ["negative", "card"],
        ["warning", "card"],
      ])
        expect(
          contrast(token(source, foreground), token(source, background)),
        ).toBeGreaterThanOrEqual(4.5);
    });
  }
  it("system dark and explicit dark use identical semantic colors", () => {
    const system = block(':root:not([data-theme="light"])');
    const explicit = block(':root[data-theme="dark"]');
    for (const name of [
      "background",
      "foreground",
      "card",
      "primary",
      "info",
      "ring",
      "chart-1",
      "chart-2",
    ]) {
      expect(token(system, name)).toBe(token(explicit, name));
    }
  });
});
