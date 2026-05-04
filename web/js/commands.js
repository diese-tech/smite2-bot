import { deleteCustomCommand, getCustomCommands, saveCustomCommand } from "./api.js";
import { $, escapeHtml, showToast } from "./ui.js";

const DEFAULT_GUILD_ID = "global";

export function initCommands() {
  $("#command-config-form")?.addEventListener("submit", saveCommandConfig);
  $("#command-list-refresh")?.addEventListener("click", loadCustomCommands);
}

export async function loadCustomCommands() {
  const list = $("#custom-command-list");

  if (!list) {
    return;
  }

  try {
    const payload = await getCustomCommands(DEFAULT_GUILD_ID);
    renderCommands(payload.commands || []);
  } catch (error) {
    list.innerHTML = `<p class="empty-state">${error.status === 401 ? "Admin login required." : "Custom commands unavailable."}</p>`;
  }
}

async function saveCommandConfig(event) {
  event.preventDefault();

  const payload = {
    guild_id: DEFAULT_GUILD_ID,
    trigger: $("#command-trigger")?.value || "",
    response: $("#command-response")?.value || "",
    channel: $("#command-channel")?.value || "",
    role_gate: $("#command-role")?.value || "Everyone",
    cooldown: $("#command-cooldown")?.value || "0s",
    enabled: $("#command-enabled")?.checked ?? true,
  };

  try {
    const result = await saveCustomCommand(payload);
    renderCommands(result.commands || [result.command]);
    showToast(`${result.command.trigger} saved locally.`);
  } catch (error) {
    showToast(error.message || "Custom command save failed.");
  }
}

function renderCommands(commands) {
  const list = $("#custom-command-list");

  if (!list) {
    return;
  }

  if (!commands.length) {
    list.innerHTML = `<p class="empty-state">No custom command configs saved yet.</p>`;
    return;
  }

  list.innerHTML = commands.map((command) => `
    <article class="custom-command-row">
      <div>
        <strong>${escapeHtml(command.trigger)}</strong>
        <span>${escapeHtml(command.channel || "All channels")} / ${escapeHtml(command.role_gate || "Everyone")}</span>
      </div>
      <span class="pill ${command.enabled ? "live" : "prototype"}">${command.enabled ? "Enabled" : "Disabled"}</span>
      <button class="button button-secondary" type="button" data-delete-command="${escapeHtml(command.trigger)}">Delete</button>
    </article>
  `).join("");

  list.querySelectorAll("[data-delete-command]").forEach((button) => {
    button.addEventListener("click", async () => {
      const trigger = button.dataset.deleteCommand;
      try {
        const result = await deleteCustomCommand(DEFAULT_GUILD_ID, trigger);
        renderCommands(result.commands || []);
        showToast(`${trigger} deleted locally.`);
      } catch (error) {
        showToast(error.message || "Custom command delete failed.");
      }
    });
  });
}
