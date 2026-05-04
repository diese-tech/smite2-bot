import {
  fallbackBuild,
  fallbackGod,
  fallbackRollTeam,
  godImageUrl,
  isApiOnline,
  roleLabels,
  rollBuild as apiRollBuild,
  rollGod as apiRollGod,
  rollTeam as apiRollTeam,
  runCommand,
} from "./api.js";
import { $, $all, showToast } from "./ui.js";

let selectedRole = "jungle";
let selectedSource = "website";
let selectedBuildRole = "adc";
let selectedBuildType = "standard";
let selectedTeamPick = null;

export function initRandomizer() {
  $all("[data-role]").forEach((chip) => {
    chip.addEventListener("click", () => {
      selectedRole = chip.dataset.role;
      $all("[data-role]").forEach((item) => item.classList.toggle("is-active", item === chip));
      rollSingleGod();
    });
  });

  $all("[data-source]").forEach((chip) => {
    chip.addEventListener("click", () => {
      selectedSource = chip.dataset.source;
      $all("[data-source]").forEach((item) => item.classList.toggle("is-active", item === chip));
      rollSingleGod();
    });
  });

  $all("[data-build-role]").forEach((chip) => {
    chip.addEventListener("click", () => {
      selectedBuildRole = chip.dataset.buildRole;
      selectedBuildType = chip.dataset.buildType || "";
      $all("[data-build-role]").forEach((item) => item.classList.toggle("is-active", item === chip));
      rollBuild();
    });
  });

  $(".random-roll")?.addEventListener("click", rollSingleGod);
  $("#roll-team-button")?.addEventListener("click", rollTeam);
  $("#build-roll-button")?.addEventListener("click", rollBuild);
  $("#web-command-run")?.addEventListener("click", runWebCommand);

  rollSingleGod();
  rollTeam();
  rollBuild();
}

async function rollSingleGod() {
  try {
    const payload = await apiRollGod(selectedRole, selectedSource);
    renderSingleGod(payload.god);
  } catch {
    renderSingleGod(fallbackGod(selectedRole, selectedSource));
  }
}

function renderSingleGod(god) {
  const roleLabel = roleLabels[god.role || selectedRole] || "Any";
  const portrait = $("#random-god-image");

  $("#random-role").textContent = roleLabel;
  $("#random-god").textContent = god.name;
  $("#random-command").textContent = god.command || ".rg";
  $("#random-subtitle").textContent = [god.class, god.pantheon].filter(Boolean).join(" / ") || "Smite 2 god pick";

  if (portrait) {
    portrait.src = god.imageUrl || godImageUrl(god.name);
    portrait.alt = `${god.name} god portrait`;
  }
}

async function rollTeam() {
  try {
    const payload = await apiRollTeam(selectedRole, selectedSource);
    renderRollTeam(payload.gods);
  } catch {
    renderRollTeam(fallbackRollTeam(selectedRole, selectedSource));
  }
}

function renderRollTeam(gods) {
  const container = $("#roll-team-results");

  if (!container) {
    return;
  }

  selectedTeamPick = null;
  container.innerHTML = gods.map((god, index) => {
    const name = god.name || god;
    const role = roleLabels[god.role || selectedRole] || "Any";
    const subtitle = [god.class, god.pantheon].filter(Boolean).join(" / ") || "Pick option";

    return `
      <button class="god-option-card" type="button" data-pick-index="${index}" aria-pressed="false">
        <span class="god-option-index">${index + 1}</span>
        <span class="asset-slot asset-slot--god-card" data-asset-slot="god-card 160x240 portrait">
          <img src="${god.imageUrl || godImageUrl(name)}" alt="${name} god portrait" />
        </span>
        <strong>${name}</strong>
        <small>${subtitle}</small>
        <span class="god-option-role">
          <span class="asset-slot asset-slot--role-icon" data-asset-slot="role-icon 32x32 svg">${role.slice(0, 1)}</span>
          ${role}
        </span>
        <span class="pick-affordance">Pick this one</span>
      </button>
    `;
  }).join("");

  $all("[data-pick-index]", container).forEach((card) => {
    card.addEventListener("click", () => selectTeamPick(card));
  });
}

function selectTeamPick(card) {
  selectedTeamPick = card.dataset.pickIndex;
  $all("[data-pick-index]").forEach((item) => {
    const selected = item.dataset.pickIndex === selectedTeamPick;
    item.classList.toggle("is-selected", selected);
    item.setAttribute("aria-pressed", String(selected));
  });
  showToast(`${card.querySelector("strong")?.textContent || "God"} selected for this roll.`);
}

function renderBuild(build) {
  const slots = $("#build-slots");
  const label = $("#build-command-label");

  if (slots) {
    slots.innerHTML = build.items.map((item) => `<div>${item}</div>`).join("");
  }

  if (label) {
    label.textContent = build.command || "Local demo build";
  }
}

async function rollBuild() {
  const count = Math.max(1, Math.min(6, Number($("#build-count")?.value || 6)));

  try {
    const payload = await apiRollBuild(selectedBuildRole, selectedBuildType, count);
    renderBuild(payload.build);
  } catch {
    renderBuild(fallbackBuild(selectedBuildRole, selectedBuildType, count));
  }
}

function formatCommandResult(result) {
  if (!result) {
    return "No result returned.";
  }

  if (result.kind === "god") {
    return `${result.god.command}\nRolled: ${result.god.name}\nRole: ${roleLabels[result.god.role] || "Any"}\nSource: ${result.god.source}`;
  }

  if (result.kind === "roll5") {
    return result.gods.map((god, index) => `${index + 1}. ${god.name}`).join("\n");
  }

  if (result.kind === "build") {
    return `${result.build.command}\n${result.build.items.map((item, index) => `${index + 1}. ${item}`).join("\n")}`;
  }

  return result.message || JSON.stringify(result, null, 2);
}

async function runWebCommand() {
  const input = $("#web-command-input");
  const output = $("#web-command-output");

  if (!input || !output) {
    return;
  }

  try {
    const payload = await runCommand(input.value);
    output.textContent = formatCommandResult(payload.result);
  } catch (error) {
    output.textContent = `Local API unavailable.\n\nStart it with:\npython web_api/server.py\n\n${error.message || ""}`;
    if (isApiOnline()) {
      showToast("Command runner could not reach the local API.");
    }
  }
}
