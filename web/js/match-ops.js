import { createMatch, demoLedger, getLedger, getWinPools, resolveProp, resolveWinner, setMatchStatus } from "./api.js";
import { $, showToast } from "./ui.js";

const statusLabels = {
  betting_open: "Betting open",
  in_progress: "In progress",
  completed: "Completed",
  settled: "Settled",
};

let activeLedger = demoLedger;

export function initMatchOps() {
  $("#match-refresh")?.addEventListener("click", loadMatches);
  $("#match-create-form")?.addEventListener("submit", submitCreateMatch);
  $("#match-status-form")?.addEventListener("submit", submitStatusChange);
  $("#match-resolve-form")?.addEventListener("submit", submitWinnerResolve);
  $("#match-prop-resolve-form")?.addEventListener("submit", submitPropResolve);
}

export async function loadMatches() {
  try {
    activeLedger = await getLedger();
  } catch (error) {
    if (error.status === 401) {
      showToast("Admin login required.");
      renderMatches([]);
      return activeLedger;
    }
    activeLedger = demoLedger;
  }

  renderMatches(activeLedger.matches || []);
  return activeLedger;
}

function renderMatches(matches) {
  const container = $("#active-matches");

  if (!container) {
    return;
  }

  if (!matches.length) {
    container.innerHTML = `<p class="empty-state">No matches in the current ledger.</p>`;
    return;
  }

  container.innerHTML = matches.map((match) => {
    const pools = getWinPools(match);
    const poolRows = Object.entries(pools)
      .map(([team, total]) => `<span>${team}: <strong>${total} pts</strong></span>`)
      .join("");

    return `
      <article class="match-row">
        <div>
          <strong>${match.match_id}</strong>
          <span>${match.teams?.team1 || "Team 1"} vs ${match.teams?.team2 || "Team 2"}</span>
        </div>
        <span class="status-badge status-badge--${match.status}">${statusLabels[match.status] || match.status}</span>
        <div class="pool-totals">${poolRows}</div>
      </article>
    `;
  }).join("");
}

async function submitCreateMatch(event) {
  event.preventDefault();
  const team1 = $("#match-team1")?.value.trim();
  const team2 = $("#match-team2")?.value.trim();

  if (!team1 || !team2) {
    showToast("Enter both team names before creating a match.");
    return;
  }

  try {
    const payload = await createMatch(team1, team2);
    showToast(`${payload.match.match_id} created.`);
    event.currentTarget.reset();
    await loadMatches();
  } catch (error) {
    showToast(error.message || "Create match failed. Demo data remains visible.");
  }
}

async function submitStatusChange(event) {
  event.preventDefault();
  const match_id = $("#match-status-id")?.value.trim();
  const status = $("#match-status-value")?.value;

  if (!match_id || !status) {
    showToast("Choose a match ID and status.");
    return;
  }

  try {
    await setMatchStatus(match_id, status);
    showToast(`${match_id.toUpperCase()} moved to ${statusLabels[status]}.`);
    await loadMatches();
  } catch (error) {
    showToast(error.message || "Status update failed.");
  }
}

async function submitWinnerResolve(event) {
  event.preventDefault();
  const match_id = $("#match-resolve-id")?.value.trim();
  const winner = $("#match-winner")?.value.trim();

  if (!match_id || !winner) {
    showToast("Enter a match ID and winner.");
    return;
  }

  try {
    const payload = await resolveWinner(match_id, winner);
    showToast(`${match_id.toUpperCase()} resolved. ${payload.payouts.length} payouts applied.`);
    await loadMatches();
  } catch (error) {
    showToast(error.message || "Winner resolution failed.");
  }
}

async function submitPropResolve(event) {
  event.preventDefault();
  const match_id = $("#match-prop-id")?.value.trim();
  const player = $("#match-prop-player")?.value.trim();
  const stat = $("#match-prop-stat")?.value.trim();
  const actual_value = Number($("#match-prop-actual")?.value || "");

  if (!match_id || !player || !stat || Number.isNaN(actual_value)) {
    showToast("Enter match ID, player, stat, and actual value.");
    return;
  }

  try {
    const payload = await resolveProp({ match_id, player, stat, actual_value });
    showToast(payload.had_bets ? `${match_id.toUpperCase()} prop resolved. ${payload.payouts.length} payouts applied.` : "No matching prop bets found.");
    await loadMatches();
  } catch (error) {
    showToast(error.message || "Prop resolution failed.");
  }
}
