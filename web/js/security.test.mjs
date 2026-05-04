import { escapeHtml } from "./security.js";

const input = `<img src=x onerror=alert(1)> & ' "`;
const expected = "&lt;img src=x onerror=alert(1)&gt; &amp; &#39; &quot;";
const actual = escapeHtml(input);

if (actual !== expected) {
  throw new Error(`escapeHtml mismatch: ${actual}`);
}

console.log("Security helpers passed.");
