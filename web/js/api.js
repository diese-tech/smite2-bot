export const API_BASE = window.location.port === "5173" ? "http://localhost:8787" : "";

export const roleLabels = {
  jungle: "Jungle",
  mid: "Mid",
  adc: "ADC",
  support: "Support",
  solo: "Solo",
  all: "Any",
};

export const roleCodes = {
  jungle: "j",
  mid: "m",
  adc: "a",
  support: "s",
  solo: "o",
};

// DEMO: God fallback objects mirror the web API God object shape.
export const demoGods = {
  jungle: [
    demoGod("Thor", "jungle", "Norse", "Assassin"),
    demoGod("Loki", "jungle", "Norse", "Assassin"),
    demoGod("Susano", "jungle", "Japanese", "Assassin"),
    demoGod("Pele", "jungle", "Polynesian", "Assassin"),
    demoGod("Hun Batz", "jungle", "Maya", "Assassin"),
  ],
  mid: [
    demoGod("Ra", "mid", "Egyptian", "Mage"),
    demoGod("Zeus", "mid", "Greek", "Mage"),
    demoGod("Morgan Le Fay", "mid", "Arthurian", "Mage"),
    demoGod("Sol", "mid", "Norse", "Mage"),
    demoGod("The Morrigan", "mid", "Celtic", "Mage"),
  ],
  adc: [
    demoGod("Neith", "adc", "Egyptian", "Hunter"),
    demoGod("Hou Yi", "adc", "Chinese", "Hunter"),
    demoGod("Cupid", "adc", "Roman", "Hunter"),
    demoGod("Anhur", "adc", "Egyptian", "Hunter"),
    demoGod("Izanami", "adc", "Japanese", "Hunter"),
  ],
  support: [
    demoGod("Ymir", "support", "Norse", "Guardian"),
    demoGod("Ares", "support", "Greek", "Guardian"),
    demoGod("Geb", "support", "Egyptian", "Guardian"),
    demoGod("Athena", "support", "Greek", "Guardian"),
    demoGod("Khepri", "support", "Egyptian", "Guardian"),
  ],
  solo: [
    demoGod("Bellona", "solo", "Roman", "Warrior"),
    demoGod("Hercules", "solo", "Roman", "Warrior"),
    demoGod("Chaac", "solo", "Maya", "Warrior"),
    demoGod("Odin", "solo", "Norse", "Warrior"),
    demoGod("Sun Wukong", "solo", "Chinese", "Warrior"),
  ],
};
demoGods.all = [
  demoGods.jungle[0],
  demoGods.support[0],
  demoGods.mid[3],
  demoGods.adc[0],
  demoGods.solo[0],
  demoGods.mid[0],
  demoGods.support[3],
].map((god) => ({ ...god, role: null, command: ".rg" }));

// DEMO: Build fallback objects mirror the web API Build object shape.
export const demoBuilds = {
  adc: ["Deathbringer", "The Executioner", "Qin's Sais", "Dominance", "Asi", "Titan's Bane"],
  mid: ["Book of Thoth", "Spear of Desolation", "Obsidian Shard", "Soul Reaver", "Rod of Tahuti", "Chronos' Pendant"],
  jungle: ["Jotunn's Wrath", "Hydra's Lament", "Brawler's Beat Stick", "Serrated Edge", "Heartseeker", "Titan's Bane"],
  solo: ["Gladiator's Shield", "Mystical Mail", "Genji's Guard", "Bluestone Brooch", "Pridwen", "Spirit Robe"],
  support: ["Thebes", "Sovereignty", "Heartward Amulet", "Relic Dagger", "Pridwen", "Spectral Armor"],
  chaos: ["A random starter", "A greedy power spike", "One defensive flex", "One utility flex", "A finisher", "Wildcard"],
};

// DEMO: Ledger fallback mirrors data/weekly_ledger.json and bot match fields.
export const demoLedger = {
  matches: [
    {
      match_id: "GF-0007",
      teams: { team1: "Solaris", team2: "Onyx" },
      status: "betting_open",
      bets: [
        { type: "win", user_id: 101, username: "AtlasMain", team: "Solaris", amount: 300 },
        { type: "win", user_id: 102, username: "NeithEnjoyer", team: "Onyx", amount: 220 },
        { type: "prop", user_id: 103, username: "WardBoss", player: "Solaris ADC", stat: "kills", direction: "over", threshold: 7.5, amount: 120 },
      ],
      result: null,
      winner: null,
      resolved_props: [],
    },
    {
      match_id: "GF-0008",
      teams: { team1: "Ember", team2: "Vale" },
      status: "in_progress",
      bets: [
        { type: "win", user_id: 104, username: "SoloDiff", team: "Vale", amount: 500 },
      ],
      result: null,
      winner: null,
      resolved_props: [],
    },
  ],
  embed_message_id: null,
  embed_channel_id: null,
};

// DEMO: Wallet fallback mirrors data/wallets.json keyed by user id.
export const demoWallets = {
  101: { username: "AtlasMain", balance: 1320 },
  102: { username: "NeithEnjoyer", balance: 980 },
  103: { username: "WardBoss", balance: 740 },
  104: { username: "SoloDiff", balance: 510 },
};

// DEMO: Draft fallback mirrors /api/draft/start response shape.
export const demoDraft = {
  draftId: "WEB-DEMO",
  gameNumber: 1,
  phase: "Ban Phase",
  step: 0,
  complete: false,
  currentTurn: { team: "blue", action: "ban" },
  blueCaptain: "AtlasMain",
  redCaptain: "NeithEnjoyer",
  bans: { blue: [], red: [] },
  picks: { blue: [], red: [] },
  fearlessPool: [],
  unavailableGods: [],
};

let apiOnline = false;

export function isApiOnline() {
  return apiOnline;
}

export function setApiOnline(online) {
  apiOnline = online;
}

export async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();

  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.error || "Godforge API request failed.");
    error.status = response.status;
    throw error;
  }

  return payload;
}

export async function getHealth() {
  return fetchJson("/api/health");
}

export async function getAuthStatus() {
  return fetchJson("/api/auth/status");
}

export async function getAdminStatus() {
  return fetchJson("/api/admin/status");
}

export async function syncLedgerEmbed() {
  return fetchJson("/api/admin/sync/ledger", { method: "POST" });
}

export async function getSettings(guild_id = "global") {
  return fetchJson(`/api/settings?guild_id=${encodeURIComponent(guild_id)}`);
}

export async function saveSettings(payload) {
  return fetchJson("/api/settings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function login(password) {
  return fetchJson("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export async function logout() {
  return fetchJson("/api/auth/logout", { method: "POST" });
}

export async function rollGod(role, source) {
  return fetchJson(`/api/gods/roll?role=${encodeURIComponent(role)}&source=${encodeURIComponent(source)}`);
}

export async function rollTeam(role, source) {
  return fetchJson(`/api/gods/roll5?role=${encodeURIComponent(role)}&source=${encodeURIComponent(source)}`);
}

export async function rollBuild(role, type, count) {
  return fetchJson(`/api/builds/roll?role=${encodeURIComponent(role)}&type=${encodeURIComponent(type || "")}&count=${count}`);
}

export async function runCommand(message) {
  return fetchJson("/api/command", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function startDraft(payload) {
  return fetchJson("/api/draft/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function submitDraftAction(payload) {
  return fetchJson("/api/draft/action", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function undoDraft(draftId) {
  return fetchJson("/api/draft/undo", {
    method: "POST",
    body: JSON.stringify({ draftId }),
  });
}

export async function getLedger() {
  return fetchJson("/api/ledger");
}

export async function createMatch(team1, team2) {
  return fetchJson("/api/match/create", {
    method: "POST",
    body: JSON.stringify({ team1, team2 }),
  });
}

export async function setMatchStatus(match_id, status) {
  return fetchJson("/api/match/status", {
    method: "POST",
    body: JSON.stringify({ match_id, status }),
  });
}

export async function resolveWinner(match_id, winner) {
  return fetchJson("/api/match/resolve/winner", {
    method: "POST",
    body: JSON.stringify({ match_id, winner }),
  });
}

export async function resolveProp(payload) {
  return fetchJson("/api/match/resolve/prop", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function placeBet(payload) {
  return fetchJson("/api/bet/place", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getWallets() {
  return fetchJson("/api/wallets");
}

export async function adjustWallet(payload) {
  return fetchJson("/api/wallet/adjust", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function resetLedger() {
  return fetchJson("/api/ledger/reset", { method: "POST" });
}

export function fallbackGod(role = "jungle", source = "website", index = Date.now()) {
  const pool = demoGods[role] || demoGods.all;
  const base = pool[Math.abs(index) % pool.length];
  const code = roleCodes[role];
  return {
    ...base,
    role: role === "all" ? null : base.role,
    source,
    command: code ? `.rg${code}${source === "tab" ? "t" : "w"}` : ".rg",
    imageUrl: base.imageUrl || godImageUrl(base.name),
  };
}

export function fallbackRollTeam(role = "jungle", source = "website") {
  const pool = demoGods[role] || demoGods.all;
  return pool.slice(0, 5).map((god) => ({
    ...god,
    role: role === "all" ? null : god.role,
    source,
    command: `.roll5${roleCodes[role] || ""}${source === "tab" && roleCodes[role] ? "t" : roleCodes[role] ? "w" : ""}`,
    imageUrl: god.imageUrl || godImageUrl(god.name),
  }));
}

export function fallbackBuild(role, type, count) {
  const items = (demoBuilds[role] || demoBuilds.adc).slice(0, count);
  return {
    role,
    type,
    count,
    items,
    command: isApiOnline() ? "Build unavailable" : "Demo fallback build",
  };
}

export function walletsToRows(wallets) {
  return Object.entries(wallets || {})
    .map(([user_id, wallet]) => ({ user_id, username: wallet.username, balance: Number(wallet.balance || 0) }))
    .sort((a, b) => b.balance - a.balance);
}

export function getWinPools(match) {
  const teams = match?.teams || {};
  const pools = { [teams.team1 || "Team 1"]: 0, [teams.team2 || "Team 2"]: 0 };
  (match?.bets || []).forEach((bet) => {
    if (bet.type === "win" && Object.prototype.hasOwnProperty.call(pools, bet.team)) {
      pools[bet.team] += Number(bet.amount || 0);
    }
  });
  return pools;
}

export function godImageUrl(name) {
  return `https://www.smitefire.com/images/v2/god/icon/${slugifyGod(name)}.png`;
}

export function slugifyGod(name) {
  return String(name).toLowerCase().replace(/'/g, "").replace(/\s+/g, "-");
}

function demoGod(name, role, pantheon, godClass) {
  return {
    name,
    role,
    source: "website",
    command: `.rg${roleCodes[role]}w`,
    imageUrl: godImageUrl(name),
    pantheon,
    class: godClass,
  };
}
