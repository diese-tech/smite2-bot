import { getAdminStatus, getAuthStatus, getHealth, login, logout, setApiOnline, syncLedgerEmbed } from "./api.js";
import { initBetting, loadBetting } from "./betting.js";
import { initDraft } from "./draft.js";
import { initMatchOps, loadMatches } from "./match-ops.js";
import { initRandomizer } from "./randomizer.js";
import { escapeHtml } from "./security.js";

export { escapeHtml };

export const dashboardTitles = {
  overview: "Overview",
  commands: "Command Config",
  randomizer: "Randomizer",
  builds: "Builds",
  drafts: "Drafts",
  match: "Match Ops",
  betting: "Betting and Wallets",
  settings: "Settings",
};

let isAuthenticated = false;

export function $(selector, root = document) {
  return root.querySelector(selector);
}

export function $all(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

export function showToast(message = "Demo only: Discord auth is planned, not active in this static prototype.") {
  const toast = $("[data-toast]");

  if (!toast) {
    return;
  }

  toast.textContent = message;
  toast.classList.add("is-visible");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    toast.classList.remove("is-visible");
  }, 3200);
}

function setApiStatus(online) {
  setApiOnline(online);
  const status = $("#api-status");

  if (!status) {
    return;
  }

  status.textContent = online ? "Local API online" : "API fallback mode";
  status.classList.toggle("live", online);
  status.classList.toggle("prototype", !online);
}

async function loadAdminStatus() {
  const summary = $("#admin-status-summary");
  const guildList = $("#admin-guild-list");
  const syncState = $("#admin-sync-state");

  if (!summary && !guildList && !syncState) {
    return;
  }

  try {
    const payload = await getAdminStatus();
    const status = payload.status || {};
    const bot = status.bot || {};
    const data = status.data || {};
    const statusCounts = data.statusCounts || {};

    if (summary) {
      summary.innerHTML = `
        <article class="ops-stat">
          <span>Bot</span>
          <strong>${bot.connected ? "Online" : "Offline"}</strong>
          <small>${escapeHtml(bot.user || "No Discord client detected")}</small>
        </article>
        <article class="ops-stat">
          <span>Guilds</span>
          <strong>${bot.guildCount ?? 0}</strong>
          <small>${bot.latencyMs === null || bot.latencyMs === undefined ? "Latency unavailable" : `${bot.latencyMs}ms latency`}</small>
        </article>
        <article class="ops-stat">
          <span>Ledger</span>
          <strong>${data.matchCount ?? 0}</strong>
          <small>${data.embedConfigured ? "Discord embed linked" : "Embed pointer missing"}</small>
        </article>
        <article class="ops-stat">
          <span>Wallets</span>
          <strong>${data.walletCount ?? 0}</strong>
          <small>${status.draftRooms ?? 0} active web draft rooms</small>
        </article>
      `;
    }

    if (guildList) {
      const guilds = bot.guilds || [];
      guildList.innerHTML = guilds.length
        ? guilds.map((guild) => `<span>${escapeHtml(guild.name)}</span>`).join("")
        : `<span>No guilds reported yet.</span>`;
    }

    if (syncState) {
      syncState.textContent = `Open ${statusCounts.betting_open || 0} / live ${statusCounts.in_progress || 0} / completed ${statusCounts.completed || 0} / settled ${statusCounts.settled || 0}`;
    }
  } catch (error) {
    if (summary) {
      summary.innerHTML = `<p class="empty-state">${error.status === 401 ? "Admin login required." : "Status unavailable."}</p>`;
    }
    if (guildList) {
      guildList.innerHTML = `<span>Login required</span>`;
    }
    if (syncState) {
      syncState.textContent = "Locked";
    }
  }
}

async function checkApiHealth() {
  try {
    await getHealth();
    setApiStatus(true);
  } catch {
    setApiStatus(false);
  }
}

function activateDashboardTab(tabName) {
  const targetPanel = $(`[data-dashboard-panel="${tabName}"]`);
  const protectedPanel = Boolean(targetPanel?.dataset.adminPanel !== undefined);

  $all("[data-dashboard-tab]").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.dashboardTab === tabName);
  });

  $all("[data-dashboard-panel]").forEach((panel) => {
    const locked = panel.dataset.adminPanel !== undefined && !isAuthenticated;
    panel.classList.toggle("is-locked", locked);
    panel.classList.toggle("is-active", panel.dataset.dashboardPanel === tabName && !locked);
  });

  const title = $("#dashboard-title");

  if (title) {
    title.textContent = dashboardTitles[tabName] || "Dashboard";
  }

  $("#admin-login-panel")?.classList.toggle("is-visible", protectedPanel && !isAuthenticated);

  if (isAuthenticated && tabName === "match") {
    loadMatches();
  }
  if (isAuthenticated && tabName === "betting") {
    loadBetting();
  }
  if (isAuthenticated && tabName === "overview") {
    loadAdminStatus();
  }
}

function activateToolTab(tabName) {
  const targetPanel = $(`[data-tool-panel="${tabName}"]`);
  const protectedPanel = Boolean(targetPanel?.dataset.adminPanel !== undefined);

  $all("[data-tool-tab]").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.toolTab === tabName);
  });

  $all("[data-tool-panel]").forEach((panel) => {
    const locked = panel.dataset.adminPanel !== undefined && !isAuthenticated;
    panel.classList.toggle("is-locked", locked);
    panel.classList.toggle("is-active", panel.dataset.toolPanel === tabName && !locked);
  });

  $("#admin-login-panel")?.classList.toggle("is-visible", protectedPanel && !isAuthenticated);
}

function updateCommandPreview() {
  const trigger = $("#command-trigger");
  const response = $("#command-response");
  const role = $("#command-role");
  const cooldown = $("#command-cooldown");
  const enabled = $("#command-enabled");

  if (!trigger || !response || !role || !cooldown || !enabled) {
    return;
  }

  $("#preview-trigger").textContent = trigger.value || ".custom";
  $("#preview-response").textContent = response.value || "Write the response your server should see.";
  $("#preview-role").textContent = role.value;
  $("#preview-cooldown").textContent = `${cooldown.value || "0s"} cooldown`;
  $("#preview-enabled").textContent = enabled.checked ? "Enabled" : "Disabled";
}

function bindNavigation() {
  $all("[data-dashboard-tab]").forEach((tab) => {
    tab.addEventListener("click", () => activateDashboardTab(tab.dataset.dashboardTab));
  });

  $all("[data-tool-tab]").forEach((tab) => {
    tab.addEventListener("click", () => activateToolTab(tab.dataset.toolTab));
  });

  $all('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const targetId = link.getAttribute("href");

      if (!targetId || targetId === "#") {
        event.preventDefault();
        return;
      }

      const target = $(targetId);

      if (target) {
        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

function bindCommandPreview() {
  $all("#command-trigger, #command-response, #command-role, #command-cooldown, #command-enabled").forEach((field) => {
    field.addEventListener("input", updateCommandPreview);
    field.addEventListener("change", updateCommandPreview);
  });
}

function bindDemoActions() {
  $all("[data-demo-action='connect']").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      showToast();
    });
  });
}

function setAuthState(authenticated, configured = true) {
  isAuthenticated = authenticated;
  const authStatus = $("#auth-status");
  const logoutButton = $("#admin-logout");
  const activeTab = $("[data-dashboard-tab].is-active")?.dataset.dashboardTab || "overview";
  const activeToolTab = $("[data-tool-tab].is-active")?.dataset.toolTab || "single-roll";

  if (authStatus) {
    authStatus.textContent = authenticated ? "Admin unlocked" : configured ? "Admin locked" : "Admin password missing";
    authStatus.classList.toggle("live", authenticated);
    authStatus.classList.toggle("prototype", !authenticated);
  }

  logoutButton?.classList.toggle("is-hidden", !authenticated);
  activateDashboardTab(activeTab);
  activateToolTab(activeToolTab);
}

async function refreshAuthStatus() {
  try {
    const status = await getAuthStatus();
    setAuthState(Boolean(status.authenticated), Boolean(status.configured));
    if (status.authenticated) {
      await Promise.all([loadMatches(), loadBetting()]);
    }
  } catch {
    setAuthState(false, false);
  }
}

function bindAuth() {
  $("#admin-login-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = $("#admin-password")?.value || "";

    try {
      await login(password);
      $("#admin-password").value = "";
      setAuthState(true, true);
      showToast("Admin dashboard unlocked.");
      await Promise.all([loadMatches(), loadBetting(), loadAdminStatus()]);
    } catch (error) {
      showToast(error.message || "Admin login failed.");
    }
  });

  $("#admin-logout")?.addEventListener("click", async () => {
    try {
      await logout();
    } finally {
      setAuthState(false, true);
      showToast("Admin dashboard locked.");
    }
  });
}

function bindAdminControls() {
  $("#admin-status-refresh")?.addEventListener("click", loadAdminStatus);
  $("#admin-sync-ledger")?.addEventListener("click", async () => {
    try {
      const payload = await syncLedgerEmbed();
      showToast(payload.discord_embed_update ? "Discord ledger refresh queued." : "Discord bot loop is not available.");
      await loadAdminStatus();
    } catch (error) {
      showToast(error.message || "Discord sync failed.");
    }
  });
}

function init() {
  bindNavigation();
  bindCommandPreview();
  bindDemoActions();
  bindAuth();
  bindAdminControls();
  initRandomizer();
  initDraft();
  initMatchOps();
  initBetting();
  checkApiHealth();
  refreshAuthStatus();
  updateCommandPreview();
}

init();
