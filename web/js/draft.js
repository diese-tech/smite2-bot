import { startDraft as apiStartDraft, submitDraftAction as apiSubmitDraftAction, undoDraft as apiUndoDraft } from "./api.js";
import { $, showToast } from "./ui.js";

let currentDraft = null;

export function initDraft() {
  $("#draft-start")?.addEventListener("click", startDraft);
  $("#draft-action")?.addEventListener("click", submitDraftAction);
  $("#draft-undo")?.addEventListener("click", undoDraft);
}

function renderDraft(draft) {
  currentDraft = draft;

  $("#draft-id-label").textContent = draft ? draft.draftId : "No draft";
  $("#draft-turn-label").textContent = draft?.currentTurn
    ? `${draft.currentTurn.team.toUpperCase()} ${draft.currentTurn.action.toUpperCase()}`
    : "Draft complete";
  $("#draft-phase-label").textContent = draft ? `${draft.phase} - Game ${draft.gameNumber}` : "Uses the same local turn order as the Discord fallback draft engine.";
  $("#blue-bans").textContent = draft?.bans?.blue?.join(", ") || "-";
  $("#red-bans").textContent = draft?.bans?.red?.join(", ") || "-";
  $("#blue-picks").textContent = draft?.picks?.blue?.join(", ") || "-";
  $("#red-picks").textContent = draft?.picks?.red?.join(", ") || "-";
  $("#fearless-pool").textContent = draft?.fearlessPool?.join(", ") || "None yet";
}

async function startDraft() {
  const status = $("#draft-status");

  try {
    const payload = await apiStartDraft({
      blueCaptainName: $("#blue-captain")?.value || "Blue Captain",
      redCaptainName: $("#red-captain")?.value || "Red Captain",
    });
    renderDraft(payload.draft);
    status.textContent = "Draft started through the local shared draft engine.";
  } catch (error) {
    status.textContent = "Start the local API to use shared draft logic: python web_api/server.py";
    showToast(error.message || "Draft API unavailable.");
  }
}

async function submitDraftAction() {
  const status = $("#draft-status");

  if (!currentDraft) {
    status.textContent = "Start a draft first.";
    return;
  }

  try {
    const payload = await apiSubmitDraftAction({
      draftId: currentDraft.draftId,
      action: currentDraft.currentTurn?.action,
      god: $("#draft-god-input")?.value || "",
    });
    renderDraft(payload.draft);
    status.textContent = `${payload.action.team} ${payload.action.type}: ${payload.action.god}`;
  } catch (error) {
    status.textContent = error.message || "Draft action failed.";
  }
}

async function undoDraft() {
  const status = $("#draft-status");

  if (!currentDraft) {
    status.textContent = "Start a draft first.";
    return;
  }

  try {
    const payload = await apiUndoDraft(currentDraft.draftId);
    renderDraft(payload.draft);
    status.textContent = payload.undone ? "Last draft action undone." : "Nothing to undo.";
  } catch (error) {
    status.textContent = error.message || "Undo failed.";
  }
}
