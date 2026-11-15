import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
const tokens = Object.fromEntries(
  [...css.matchAll(/--color-([\w-]+):\s*#([\da-f]{6})/gi)].map(([, name, hex]) => [name, hex]),
);
function luminance(hex) {
  return hex
    .match(/../g)
    .map((channel) => parseInt(channel, 16) / 255)
    .map((channel) => (channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4))
    .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
}
for (const [foreground, background, minimum] of [
  ["ink", "surface", 4.5],
  ["ink-muted", "canvas", 4.5],
  ["ink-muted", "surface", 4.5],
  ["surface", "forest", 4.5],
  ["copper", "canvas", 4.5],
  ["warning", "warning-wash", 4.5],
  ["danger", "danger-wash", 4.5],
  ["control-border", "surface", 3],
  ["forest", "wash", 4.5],
]) {
  test(`${foreground} on ${background} meets contrast ${minimum}:1`, () => {
    const a = luminance(tokens[foreground]);
    const b = luminance(tokens[background]);
    const contrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    assert.ok(contrast >= minimum, `${contrast.toFixed(2)}:1`);
    console.log(`${foreground}/${background}: ${contrast.toFixed(2)}:1`);
  });
}
