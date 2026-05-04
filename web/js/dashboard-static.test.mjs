import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const tabMatches = [...html.matchAll(/data-dashboard-tab="([^"]+)"/g)].map((match) => match[1]);
const panelMatches = [...html.matchAll(/data-dashboard-panel="([^"]+)"/g)].map((match) => match[1]);

const missingPanels = tabMatches.filter((tab) => !panelMatches.includes(tab));

if (missingPanels.length) {
  throw new Error(`Dashboard tabs missing panels: ${missingPanels.join(", ")}`);
}

const requiredIds = [
  "admin-login-panel",
  "admin-server-grid",
  "module-health-grid",
  "admin-audit-list",
  "custom-command-list",
  "settings-form",
  "bot-master-role-chips",
  "admin-status-summary",
];

for (const id of requiredIds) {
  if (!html.includes(`id="${id}"`)) {
    throw new Error(`Missing dashboard element: ${id}`);
  }
}

console.log("Dashboard static checks passed.");
