import { adjustWallet, demoLedger, demoWallets, getLedger, getWallets, placeBet, resetLedger, walletsToRows } from "./api.js";
import { loadMatches } from "./match-ops.js";
import { $, escapeHtml, showToast } from "./ui.js";

export function initBetting() {
  $("#wallet-adjust-form")?.addEventListener("submit", submitWalletAdjust);
  $("#place-bet-form")?.addEventListener("submit", submitPlaceBet);
  $("#bet-type")?.addEventListener("change", syncBetFields);
  $("#ledger-reset-button")?.addEventListener("click", confirmLedgerReset);
  $("#betting-refresh")?.addEventListener("click", loadBetting);
  syncBetFields();
}

export async function loadBetting() {
  await Promise.all([loadActiveBets(), loadWalletLeaderboard()]);
}

async function loadActiveBets() {
  let ledger = demoLedger;

  try {
    ledger = await getLedger();
  } catch (error) {
    if (error.status === 401) {
      showToast("Admin login required.");
      renderActiveBets([]);
      return;
    }
    ledger = demoLedger;
  }

  renderActiveBets(ledger.matches || []);
}

function renderActiveBets(matches) {
  const container = $("#active-bets");

  if (!container) {
    return;
  }

  const bets = matches.flatMap((match) => (match.bets || []).map((bet) => ({ ...bet, match_id: match.match_id })));

  if (!bets.length) {
    container.innerHTML = `<p class="empty-state">No active bets in the ledger.</p>`;
    return;
  }

  container.innerHTML = bets.map((bet) => {
    const target = bet.type === "win"
      ? bet.team
      : `${bet.player} ${bet.direction} ${bet.threshold} ${bet.stat}`;

    return `
      <article class="bet-row">
        <strong>${escapeHtml(bet.username || `User ${bet.user_id}`)}</strong>
        <span>${escapeHtml(bet.match_id)}</span>
        <span>${escapeHtml(target)}</span>
        <span>${Number(bet.amount || 0)} pts</span>
        <span class="pill prototype">${bet.type === "prop" ? "Prop" : "Win"}</span>
      </article>
    `;
  }).join("");
}

async function loadWalletLeaderboard() {
  let wallets = demoWallets;

  try {
    wallets = await getWallets();
  } catch (error) {
    if (error.status === 401) {
      renderWallets([]);
      return;
    }
    wallets = demoWallets;
  }

  renderWallets(walletsToRows(wallets));
}

function renderWallets(wallets) {
  const container = $("#wallet-leaderboard");

  if (!container) {
    return;
  }

  if (!wallets.length) {
    container.innerHTML = `<p class="empty-state">No wallets found.</p>`;
    return;
  }

  container.innerHTML = wallets.map((wallet, index) => `
    <article class="wallet-row">
      <span>${index + 1}</span>
      <strong>${escapeHtml(wallet.username || `User ${wallet.user_id}`)}</strong>
      <em>${Number(wallet.balance || 0)} pts</em>
    </article>
  `).join("");
}

async function submitWalletAdjust(event) {
  event.preventDefault();
  const target = $("#wallet-target")?.value.trim();
  const action = $("#wallet-action")?.value;
  const amount = Number($("#wallet-amount")?.value || 0);

  if (!target || !action || Number.isNaN(amount)) {
    showToast("Enter a player, action, and amount.");
    return;
  }

  try {
    const payload = await adjustWallet({ target, username: target, action, amount });
    showToast(`${payload.wallet.username} balance is now ${payload.wallet.balance} pts.`);
    await loadWalletLeaderboard();
  } catch (error) {
    showToast(error.message || "Wallet adjustment failed.");
  }
}

async function submitPlaceBet(event) {
  event.preventDefault();
  const type = $("#bet-type")?.value || "win";
  const payload = {
    match_id: $("#bet-match-id")?.value.trim(),
    username: $("#bet-bettor")?.value.trim(),
    target: $("#bet-bettor")?.value.trim(),
    amount: Number($("#bet-amount")?.value || 0),
    type,
  };

  if (type === "win") {
    payload.team = $("#bet-team")?.value.trim();
  } else {
    payload.player = $("#bet-player")?.value.trim();
    payload.stat = $("#bet-stat")?.value.trim();
    payload.direction = $("#bet-direction")?.value;
    payload.threshold = Number($("#bet-threshold")?.value || "");
  }

  if (!payload.match_id || !payload.username || !payload.amount || (type === "win" && !payload.team)) {
    showToast("Enter match, bettor, amount, and team.");
    return;
  }

  if (type === "prop" && (!payload.player || !payload.stat || !payload.direction || Number.isNaN(payload.threshold))) {
    showToast("Enter player, stat, direction, and threshold for prop bets.");
    return;
  }

  try {
    const result = await placeBet(payload);
    showToast(`${result.bet.username} bet ${result.bet.amount} pts. Balance: ${result.wallet.balance} pts.`);
    await loadBetting();
    await loadMatches();
  } catch (error) {
    showToast(error.message || "Bet placement failed.");
  }
}

function syncBetFields() {
  const type = $("#bet-type")?.value || "win";
  $("#win-bet-fields")?.classList.toggle("is-hidden", type !== "win");
  $("#prop-bet-fields")?.classList.toggle("is-hidden", type !== "prop");
}

async function confirmLedgerReset() {
  const confirmed = window.confirm("Reset the weekly ledger and clear all matches? Wallets are unaffected.");

  if (!confirmed) {
    return;
  }

  try {
    const payload = await resetLedger();
    showToast(`Ledger reset. Cleared ${payload.cleared} matches.`);
    await Promise.all([loadActiveBets(), loadMatches()]);
  } catch (error) {
    showToast(error.message || "Ledger reset failed.");
  }
}
