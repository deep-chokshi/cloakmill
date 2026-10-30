import {
  createDemoState,
  transition,
  canExport,
  canFreeze,
  pendingReviews,
} from "./model.mjs";
import { records, sources } from "./fixtures.mjs";
import { brandMark, icon } from "./icons.mjs";
import { escape, navigation, renderView, scanPhase } from "./views.mjs";

const root = document.getElementById("app");
let state = createDemoState();
const ui = {
  identityTab: "review",
  caseId: "maya",
  choices: {},
  entityId: "p017",
  previewSource: "messages",
  recordId: "r006",
  highlights: true,
  navOpen: false,
  scanProgress: 0,
  validating: false,
};
let generation = 0;
let toastTimer;
const mobileQuery = window.matchMedia("(max-width: 980px)");

function currentView() {
  const id = location.hash.replace(/^#\/?/, "");
  return navigation.some((item) => item.id === id) ? id : "overview";
}

function render({ focus = false } = {}) {
  const view = currentView();
  const active = navigation.find((item) => item.id === view);
  root.innerHTML = `<button class="mobile-overlay ${ui.navOpen ? "visible" : ""}" data-action="toggle-nav" aria-label="Close navigation" tabindex="-1"></button>
  <aside class="sidebar ${ui.navOpen ? "open" : ""}" aria-label="Workspace navigation"><button class="icon-button mobile-close" data-action="toggle-nav" aria-label="Close navigation">${icon("close")}</button><a class="brand" href="#/overview">${brandMark()}<span>CloakMill</span></a><div class="brand-label">CONTEXT, PRESERVED.</div>
  <button class="workspace-switch" data-action="new-project" aria-label="Create a demo project"><span class="workspace-icon">B</span><span><strong>Birch Data</strong><small>Fictional organization</small></span>${icon("plus")}</button>
  <div class="nav-label">WORKSPACE</div><nav>${navigation.map((item, index) => `${index === 5 ? '<div class="nav-divider"></div>' : ""}<a class="nav-link ${item.id === view ? "active" : ""}" href="#/${item.id}" data-action="navigate" data-view="${item.id}" ${item.id === view ? 'aria-current="page"' : ""}>${icon(item.icon)}<span>${item.label}</span>${item.id === "identities" && state.scanStatus === "complete" && pendingReviews(state).length ? `<span class="nav-count">${pendingReviews(state).length}</span>` : ""}</a>`).join("")}</nav>
  <div class="sidebar-bottom"><div class="local-notice"><span><i class="dot"></i>Local browser prototype</span><small>Fictional data. No uploads.</small></div><div class="sidebar-footer"><div class="person-cell"><span class="avatar">A</span><span><strong>Alex Morgan</strong><small>Demo reviewer</small></span></div><button class="icon-button" data-action="help" aria-label="Open prototype guide">${icon("help")}</button></div></div></aside>
  <div class="app-main"><div class="topbar"><button class="icon-button mobile-toggle" data-action="toggle-nav" aria-label="Open navigation" aria-expanded="${ui.navOpen}">${icon("menu")}</button><div class="breadcrumbs"><span>Workspace</span>${icon("chevron")}<strong>${escape(state.project.name)}</strong>${icon("chevron")}<span>${active.label}</span></div><div class="topbar-actions"><span class="prototype-label">INTERACTIVE PROTOTYPE</span><button class="button ghost" data-action="reset" aria-label="Reset demo">${icon("reset")}<span>Reset demo</span></button></div></div>
  <main id="main-content" class="content" tabindex="-1"><div class="page-enter">${renderView(view, state, ui)}</div><footer class="prototype-strip"><span>${icon("eye")}Fictional records and illustrative checks. No private files are read.</span><button class="text-button" data-action="help">About this prototype${icon("arrow", "small")}</button></footer></main></div>`;
  syncNavigation();
  if (focus)
    document.getElementById("main-content").focus({ preventScroll: true });
}

// Keeps a keyboard user's place when the page rebuilds for background work.
function renderKeepingFocus() {
  const { dataset = {} } = document.activeElement ?? {};
  const selector = Object.entries(dataset)
    .map(([key, value]) => {
      const name = key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
      return `[data-${name}="${CSS.escape(value)}"]`;
    })
    .join("");
  render();
  if (selector) root.querySelector(selector)?.focus({ preventScroll: true });
}

function announceScan(message) {
  document.getElementById("scan-status").textContent = message;
}

function syncNavigation() {
  const sidebar = root.querySelector(".sidebar");
  if (sidebar) sidebar.inert = mobileQuery.matches && !ui.navOpen;
  const workspace = root.querySelector(".app-main");
  if (workspace) workspace.inert = mobileQuery.matches && ui.navOpen;
}

function navigate(view) {
  if (!navigation.some((item) => item.id === view)) return;
  ui.navOpen = false;
  if (currentView() === view) render({ focus: true });
  else location.hash = `/${view}`;
  window.scrollTo({ top: 0, behavior: "instant" });
}

function notify(message) {
  const toast = document.getElementById("toast");
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("visible");
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 4200);
}

function update(event) {
  const previous = state;
  state = transition(state, event);
  if (ui.validating && previous.revision !== state.revision) {
    generation += 1;
    ui.validating = false;
  }
  return state !== previous;
}

function cancelJobs() {
  generation += 1;
  ui.validating = false;
  ui.scanProgress = 0;
}

const pause = (duration) =>
  new Promise((resolve) => setTimeout(resolve, duration));

async function scan() {
  if (!state.hasData || state.scanStatus === "running") return;
  update({ type: "START_SCAN" });
  const token = ++generation;
  ui.scanProgress = 0;
  navigate("discovery");
  render();
  announceScan("Sample scan started.");
  for (const value of [25, 65, 100]) {
    await pause(380);
    if (token !== generation) return;
    ui.scanProgress = value;
    if (currentView() === "discovery") {
      render();
      announceScan(`${scanPhase(value)}, ${value} percent.`);
    }
  }
  if (token !== generation) return;
  update({ type: "FINISH_SCAN" });
  announceScan("");
  if (currentView() === "discovery") render({ focus: true });
  else renderKeepingFocus();
  notify(
    "Sample observations are ready. The two identity decisions need review.",
  );
}

async function validate() {
  if (
    !canFreeze(state) ||
    state.frozenRevision !== state.revision ||
    ui.validating
  )
    return;
  const token = ++generation;
  ui.validating = true;
  render();
  await pause(650);
  if (token !== generation) return;
  ui.validating = false;
  update({ type: "VALIDATE" });
  render({ focus: true });
  notify(
    canExport(state)
      ? "Illustrative validation complete. You can create a sample release."
      : "The sample identity choice conflicts with the evidence. Reopen the review to correct it.",
  );
}

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (id === "project-dialog") {
    const input = document.getElementById("project-name");
    input.value = "";
    input.removeAttribute("aria-invalid");
    document.getElementById("project-error").textContent = "";
  }
  dialog.showModal();
  if (id === "project-dialog") document.getElementById("project-name").focus();
}

function download(releaseId) {
  const release = state.releases.find((item) => item.id === releaseId);
  if (!release) return;
  const blob = new Blob([JSON.stringify(release.bundle, null, 2) + "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `cloakmill-${release.id}-fictional.json`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  notify(
    "Downloaded the fictional JSON sample bundle. No private mapping registry is included.",
  );
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  const { action } = target.dataset;
  if (target.tagName === "A") event.preventDefault();
  switch (action) {
    case "navigate":
      navigate(target.dataset.view);
      break;
    case "new-project":
      openDialog("project-dialog");
      break;
    case "help":
      openDialog("help-dialog");
      break;
    case "reset":
      openDialog("reset-dialog");
      break;
    case "close-dialog":
      target.closest("dialog")?.close();
      break;
    case "confirm-reset":
      cancelJobs();
      update({ type: "RESET" });
      ui.choices = {};
      ui.identityTab = "review";
      ui.caseId = "maya";
      target.closest("dialog").close();
      navigate("overview");
      render({ focus: true });
      notify("The original fictional workspace is restored.");
      break;
    case "toggle-nav":
      ui.navOpen = !ui.navOpen;
      render();
      root
        .querySelector(ui.navOpen ? ".sidebar .mobile-close" : ".mobile-toggle")
        ?.focus();
      break;
    case "load-sample":
      cancelJobs();
      update({ type: "LOAD_SAMPLE" });
      render({ focus: true });
      notify(
        "The fictional sample dataset is loaded. No local files were read.",
      );
      break;
    case "scan":
      void scan();
      break;
    case "exclude": {
      const wasApproved = state.frozenRevision !== null;
      update({
        type: "EXCLUDE_UNSUPPORTED",
        value: target.dataset.value === "true",
      });
      render({ focus: true });
      notify(
        state.excludedUnsupported
          ? "Encrypted sample explicitly excluded from the release scope."
          : wasApproved
            ? "Encrypted sample restored to scope. Release approval is invalidated."
            : "Encrypted sample restored to scope.",
      );
      break;
    }
    case "inspect-source":
      ui.previewSource = target.dataset.source;
      ui.recordId = records.find(
        (record) => record.source === ui.previewSource,
      ).id;
      navigate("preview");
      break;
    case "identity-tab":
      ui.identityTab = target.dataset.tab;
      render({ focus: true });
      break;
    case "select-case":
      ui.caseId = target.dataset.case;
      render();
      root.querySelector(`.review-card[data-case="${ui.caseId}"]`)?.focus();
      break;
    case "choose-candidate":
      ui.choices[target.dataset.case] = target.dataset.value;
      render();
      root
        .querySelector(`.candidate[data-value="${target.dataset.value}"]`)
        ?.focus();
      break;
    case "confirm-review":
      if (!ui.choices[target.dataset.case]) return;
      update({
        type: "DECIDE",
        caseId: target.dataset.case,
        value: ui.choices[target.dataset.case],
      });
      ui.caseId = pendingReviews(state)[0]?.id || "maya";
      render({ focus: true });
      notify("Identity decision recorded for this fictional sample.");
      break;
    case "inspect-entity":
      ui.identityTab = "all";
      ui.entityId = target.dataset.entity;
      navigate("identities");
      break;
    case "select-entity":
      ui.entityId = target.dataset.entity;
      render();
      root.querySelector(`.entity-row[data-entity="${ui.entityId}"]`)?.focus();
      break;
    case "reopen": {
      const wasApproved = state.frozenRevision !== null;
      const reopened = update({ type: "REOPEN", caseId: target.dataset.case });
      ui.caseId = target.dataset.case;
      ui.identityTab = "review";
      delete ui.choices[target.dataset.case];
      navigate("identities");
      render({ focus: true });
      notify(
        !reopened
          ? "Review opened."
          : wasApproved
            ? "Review reopened. The mapping approval and validation are invalidated."
            : "Review reopened.",
      );
      break;
    }
    case "freeze":
      if (update({ type: "FREEZE" })) {
        render({ focus: true });
        notify(`Sample mapping demo-map-r${state.revision} is frozen.`);
      }
      break;
    case "select-record":
      ui.recordId = target.dataset.record;
      render();
      root
        .querySelector(`.record-choice[data-record="${ui.recordId}"]`)
        ?.focus();
      break;
    case "toggle-highlights":
      ui.highlights = !ui.highlights;
      render();
      root.querySelector('[data-action="toggle-highlights"]')?.focus();
      break;
    case "validate":
      void validate();
      break;
    case "publish":
      if (update({ type: "PUBLISH" })) {
        render({ focus: true });
        notify(
          "Fictional sample release created. Its snapshot stays unchanged if you revise the working profile.",
        );
      }
      break;
    case "download":
      download(target.dataset.release);
      break;
  }
});

document.addEventListener("change", (event) => {
  const control = event.target;
  if (control.dataset.change === "profile") {
    update({ type: "SET_PROFILE", value: control.value });
    render();
    document.getElementById("profile-select")?.focus();
    notify(
      "Sample profile changed. Freeze and validate the new revision before releasing it.",
    );
  }
  if (control.dataset.change === "preview-source") {
    ui.previewSource = control.value;
    ui.recordId = records.find((record) => record.source === control.value).id;
    render();
    document.getElementById("preview-source")?.focus();
  }
});

document.getElementById("project-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("project-name");
  try {
    const next = transition(state, {
      type: "CREATE_PROJECT",
      name: input.value,
    });
    cancelJobs();
    state = next;
    ui.choices = {};
    ui.identityTab = "review";
    ui.caseId = "maya";
    document.getElementById("project-dialog").close();
    navigate("overview");
    render({ focus: true });
    notify("Demo project created. Add the fictional sample to get started.");
  } catch (error) {
    document.getElementById("project-error").textContent = error.message;
    input.setAttribute("aria-invalid", "true");
    input.focus();
  }
});

document.addEventListener("keydown", (event) => {
  if (
    !ui.navOpen ||
    !mobileQuery.matches ||
    document.querySelector("dialog[open]")
  )
    return;
  if (event.key === "Escape") {
    ui.navOpen = false;
    render();
    root.querySelector(".mobile-toggle")?.focus();
  }
  if (event.key === "Tab") {
    const items = [
      ...root.querySelectorAll(".sidebar button, .sidebar a"),
    ].filter((item) => item.getClientRects().length && !item.disabled);
    const first = items[0],
      last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
});

for (const type of ["dragover", "drop"])
  document.addEventListener(type, (event) => {
    event.preventDefault();
    if (type === "drop")
      notify(
        "This prototype does not read dropped files. Load the fictional sample to explore.",
      );
  });

window.addEventListener("hashchange", () => render({ focus: true }));
mobileQuery.addEventListener("change", syncNavigation);
render();
