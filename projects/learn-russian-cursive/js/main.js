import {
  DEFAULT_LESSON_MODE,
  LESSON_MODES,
  MAX_PROFILES,
  MODE_LABELS,
  MODE_LANGUAGE_LABELS,
  TOTAL_LESSONS_PER_MODE,
  getLesson as getCurriculumLesson,
  getLessonText,
  getStageSample,
  stages,
} from "./curriculum.js";
import { createProfileRecord, loadState, makeProgressKey, saveState } from "./storage.js";

const app = document.querySelector("#app");
const dialog = document.querySelector("#profile-dialog");
const form = document.querySelector("#profile-form");
const cancelProfileButton = document.querySelector("#cancel-profile-button");

const state = loadState();

const route = {
  view: "profiles",
  stageId: null,
  lessonId: null,
};
const LESSON_MODE_ORDER = [LESSON_MODES.EASY, LESSON_MODES.HARD];

const STROKE_RENDER = {
  followStrength: 10,
  releaseFollowBoost: 2,
  minPointDistance: 0.85,
  maxSegmentLength: 10,
  settleDistance: 0.75,
};

const HANDWRITING_FONT = {
  family: "Propisi Runtime",
  source: 'url("./assets/fonts/Propisi-Regular.woff") format("woff")',
  style: "normal",
  weight: "400",
};

const practice = {
  rows: 3,
  showGuides: true,
  isDrawing: false,
  currentStroke: [],
  strokes: [],
  ctx: null,
  canvas: null,
  pixelRatio: 1,
  surfaceWidth: 0,
  surfaceHeight: 0,
  activePointerId: null,
  activeTouchId: null,
  inputPoint: null,
  renderPoint: null,
  strokeFrameId: null,
  lastFrameTime: 0,
};

const supportsDialog = typeof dialog?.showModal === "function";
const supportsPointerEvents = "PointerEvent" in window;
let handwritingFontLoaded = false;
let handwritingFontPromise = null;

window.addEventListener("hashchange", syncRouteFromHash);
window.addEventListener("resize", () => {
  if (route.view === "lesson") {
    scheduleLessonRefresh();
  }
});
window.addEventListener("load", refreshLessonView);
window.addEventListener("orientationchange", refreshLessonView);

cancelProfileButton.addEventListener("click", closeProfileDialog);
form.addEventListener("submit", handleCreateProfile);
dialog?.addEventListener("close", () => document.body.classList.remove("dialog-open"));
dialog?.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeProfileDialog();
});
dialog?.addEventListener("click", (event) => {
  if (event.target === dialog) {
    closeProfileDialog();
  }
});
document.fonts?.ready?.then(refreshLessonView).catch(() => {
  // Ignore font API failures and rely on the normal render path.
});

syncRouteFromHash();
render();

function syncRouteFromHash() {
  const hash = window.location.hash.replace(/^#/, "");

  if (!hash) {
    route.view = state.activeProfileId ? "stages" : "profiles";
    route.stageId = null;
    route.lessonId = null;
    return render();
  }

  const parts = hash.split("/");
  if (parts[0] === "profiles") {
    route.view = "profiles";
    route.stageId = null;
    route.lessonId = null;
  } else if (parts[0] === "stages") {
    route.view = "stages";
    route.stageId = null;
    route.lessonId = null;
  } else if (parts[0] === "lesson" && parts[1] && parts[2]) {
    route.view = "lesson";
    route.stageId = decodeURIComponent(parts[1]);
    route.lessonId = decodeURIComponent(parts[2]);
  } else {
    route.view = "profiles";
    route.stageId = null;
    route.lessonId = null;
  }

  render();
}

function render() {
  const activeProfile = getActiveProfile();

  if (!activeProfile) {
    route.view = "profiles";
  }

  if (route.view === "profiles") {
    renderProfilesView();
    return;
  }

  if (route.view === "stages") {
    renderStagesView(activeProfile);
    return;
  }

  if (route.view === "lesson") {
    const lesson = getLessonForRoute(route.stageId, route.lessonId);
    if (!lesson) {
      navigateToStages();
      return;
    }
    renderLessonView(activeProfile, lesson);
  }
}

function normalizeLessonMode(mode) {
  return mode === LESSON_MODES.HARD ? LESSON_MODES.HARD : DEFAULT_LESSON_MODE;
}

function modeLabel(mode) {
  return MODE_LABELS[normalizeLessonMode(mode)] || MODE_LABELS[DEFAULT_LESSON_MODE];
}

function languageLabel(mode) {
  return MODE_LANGUAGE_LABELS[normalizeLessonMode(mode)] || MODE_LANGUAGE_LABELS[DEFAULT_LESSON_MODE];
}

function createModeToggle({ compact = false } = {}) {
  const wrapper = document.createElement("div");
  wrapper.className = compact ? "mode-toggle compact" : "mode-toggle";

  const buttons = document.createElement("div");
  buttons.className = "mode-toggle-buttons";
  buttons.setAttribute("role", "group");
  buttons.setAttribute("aria-label", "Lesson difficulty");

  for (const mode of LESSON_MODE_ORDER) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mode-chip";
    button.textContent = modeLabel(mode);
    button.title = `${modeLabel(mode)} mode uses ${languageLabel(mode)} lessons.`;
    button.setAttribute("aria-pressed", String(mode === state.lessonMode));
    if (mode === state.lessonMode) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => setLessonLanguageMode(mode));
    buttons.append(button);
  }

  wrapper.append(buttons);

  if (!compact) {
    const copy = document.createElement("p");
    copy.className = "mode-toggle-copy section-note";
    copy.textContent = `${modeLabel(LESSON_MODES.EASY)} = ${languageLabel(LESSON_MODES.EASY)} · ${modeLabel(LESSON_MODES.HARD)} = ${languageLabel(LESSON_MODES.HARD)}`;
    wrapper.append(copy);
  }

  return wrapper;
}

function setLessonLanguageMode(mode) {
  const nextMode = normalizeLessonMode(mode);
  if (nextMode === state.lessonMode) {
    return;
  }

  if (route.view === "lesson" && route.stageId === "custom") {
    const profile = getActiveProfile();
    if (profile && !getCustomPracticeText(profile, nextMode)) {
      window.alert("Add a Russian practice name on the profile before switching Name Practice to Hard mode.");
      return;
    }
  }

  state.lessonMode = nextMode;
  saveState(state);
  render();
}

function renderProfilesView() {
  setLessonMode(false);
  destroyPracticeSurface();
  const template = document.querySelector("#profile-view-template");
  app.replaceChildren(template.content.cloneNode(true));

  const newProfileButton = document.querySelector("#new-profile-button");
  const profilesGrid = document.querySelector("#profiles-grid");

  newProfileButton.addEventListener("click", openProfileDialog);

  if (state.profiles.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No profiles yet.";
    profilesGrid.append(empty);
    return;
  }

  const cardTemplate = document.querySelector("#profile-card-template");

  for (const profile of state.profiles) {
    const node = cardTemplate.content.cloneNode(true);
    const card = node.querySelector(".profile-card");
    const avatar = node.querySelector(".avatar");
    const name = node.querySelector(".profile-name");
    const progress = node.querySelector(".profile-progress");
    const openButton = node.querySelector(".open-profile-button");
    const deleteButton = node.querySelector(".delete-profile-button");

    avatar.textContent = profile.avatar;
    name.textContent = profile.name;
    progress.textContent = profileProgressLabel(profile);

    openButton.addEventListener("click", () => {
      state.activeProfileId = profile.id;
      saveState(state);
      navigateToStages();
    });

    deleteButton.addEventListener("click", () => {
      const confirmed = window.confirm(`Delete profile "${profile.name}"?`);
      if (!confirmed) {
        return;
      }

      state.profiles = state.profiles.filter((entry) => entry.id !== profile.id);
      if (state.activeProfileId === profile.id) {
        state.activeProfileId = state.profiles[0]?.id || null;
      }
      saveState(state);
      render();
    });

    profilesGrid.append(card);
  }
}

function renderStagesView(profile) {
  setLessonMode(false);
  destroyPracticeSurface();
  ensureHandwritingFont();
  const template = document.querySelector("#stage-view-template");
  app.replaceChildren(template.content.cloneNode(true));

  document.querySelector("#stage-profile-name").textContent = profile.name;
  document.querySelector(".stage-actions")?.prepend(createModeToggle());

  document
    .querySelector("#change-profile-button")
    .addEventListener("click", () => navigateToProfiles());

  document.querySelector("#practice-name-button").addEventListener("click", () => {
    const customText = getCustomPracticeText(profile, state.lessonMode);
    if (!customText) {
      window.alert("Add a Russian practice name on the profile to use Name Practice in Hard mode.");
      return;
    }

    openLesson("custom-name");
  });

  const stagesGrid = document.querySelector("#stages-grid");
  const stageTemplate = document.querySelector("#stage-card-template");
  const chipTemplate = document.querySelector("#lesson-chip-template");

  for (const stage of stages) {
    const node = stageTemplate.content.cloneNode(true);
    const name = node.querySelector(".stage-name");
    const kicker = node.querySelector(".stage-kicker");
    const sample = node.querySelector(".stage-sample");
    const stageProgress = node.querySelector(".stage-progress");
    const progressBar = node.querySelector(".progress-bar span");
    const openStageButton = node.querySelector(".open-stage-button");
    const lessonList = node.querySelector(".lesson-list");
    const stageSample = getStageSample(stage, state.lessonMode);

    const completedCount = stage.lessons.filter((lesson) => isLessonComplete(profile, lesson.id)).length;
    const percent = Math.round((completedCount / stage.lessons.length) * 100);

    kicker.textContent = `${stage.order}`;
    name.textContent = stage.name;
    sample.textContent = stageSample;
    sample.title = stageSample;
    sample.dataset.script = state.lessonMode;
    stageProgress.textContent = `${modeLabel(state.lessonMode)} ${completedCount}/${stage.lessons.length}`;
    progressBar.style.width = `${percent}%`;

    openStageButton.addEventListener("click", () => {
      const nextLesson = stage.lessons.find((lesson) => !isLessonComplete(profile, lesson.id)) || stage.lessons[0];
      navigateToLesson(stage.id, nextLesson.id);
    });

    for (const lesson of stage.lessons) {
      const chipNode = chipTemplate.content.cloneNode(true);
      const button = chipNode.querySelector(".lesson-chip");
      const text = chipNode.querySelector(".lesson-chip-text");
      const meta = chipNode.querySelector(".lesson-chip-meta");
      const lessonText = getLessonText(lesson, state.lessonMode);
      const done = isLessonComplete(profile, lesson.id);

      text.textContent = lessonText;
      text.title = lessonText;
      text.dataset.script = state.lessonMode;
      button.title = lessonText;
      meta.textContent = done ? "Done" : "Lesson";
      if (done) {
        button.classList.add("completed");
      }
      button.addEventListener("click", () => navigateToLesson(stage.id, lesson.id));
      lessonList.append(button);
    }

    stagesGrid.append(node);
  }
}

function renderLessonView(profile, lesson) {
  setLessonMode(true);
  ensureHandwritingFont();
  const template = document.querySelector("#lesson-view-template");
  app.replaceChildren(template.content.cloneNode(true));

  const stage = stages.find((entry) => entry.id === route.stageId);
  const isCustomLesson = route.stageId === "custom";
  const displayStageName = isCustomLesson ? "Name Practice" : stage?.name || "";
  const lessonText = getLessonText(lesson, state.lessonMode);

  document.querySelector(".lesson-actions")?.prepend(createModeToggle({ compact: true }));
  document.querySelector("#lesson-stage-label").textContent = `${displayStageName} · ${modeLabel(state.lessonMode)} mode`;
  document.querySelector("#lesson-title").textContent = lessonText;
  document.querySelector("#back-to-stages-button").addEventListener("click", navigateToStages);
  document.querySelector("#toggle-guides-button").addEventListener("click", toggleGuides);
  document.querySelector("#clear-canvas-button").addEventListener("click", clearCanvas);
  document.querySelector("#complete-lesson-button").addEventListener("click", () => {
    markLessonComplete(profile, route.lessonId);
    const nextLesson = getNextLesson(route.stageId, route.lessonId);
    if (nextLesson) {
      navigateToLesson(route.stageId, nextLesson.id);
      return;
    }
    navigateToStages();
  });

  document.querySelector("#increase-rows-button").addEventListener("click", () => changeRows(1));
  document.querySelector("#decrease-rows-button").addEventListener("click", () => changeRows(-1));

  buildReferenceSheet(lessonText, state.lessonMode);
  setupPracticeSurface();
  scheduleLessonRefresh();
  updateLessonButtons();
}

function refreshLessonView() {
  if (route.view !== "lesson") {
    return;
  }

  const lesson = getLessonForRoute(route.stageId, route.lessonId);
  if (!lesson) {
    return;
  }

  buildReferenceSheet(getLessonText(lesson, state.lessonMode), state.lessonMode);
  scheduleLessonRefresh();
  updateLessonButtons();
}

function ensureHandwritingFont() {
  if (handwritingFontLoaded || !document.fonts || typeof FontFace !== "function") {
    return Promise.resolve(handwritingFontLoaded);
  }

  if (handwritingFontPromise) {
    return handwritingFontPromise;
  }

  const fontFace = new FontFace(HANDWRITING_FONT.family, HANDWRITING_FONT.source, {
    style: HANDWRITING_FONT.style,
    weight: HANDWRITING_FONT.weight,
  });

  handwritingFontPromise = fontFace
    .load()
    .then((loadedFace) => {
      document.fonts.add(loadedFace);
      handwritingFontLoaded = true;
      if (route.view === "lesson") {
        refreshLessonView();
      }
      return true;
    })
    .catch((error) => {
      console.error("Failed to load handwriting font.", error);
      handwritingFontPromise = null;
      return false;
    });

  return handwritingFontPromise;
}

function scheduleLessonRefresh(frames = 2) {
  if (route.view !== "lesson") {
    return;
  }

  let remainingFrames = Math.max(1, frames);
  const step = () => {
    if (route.view !== "lesson") {
      return;
    }

    syncCanvasResolution();
    redrawCanvas();

    remainingFrames -= 1;
    if (remainingFrames > 0) {
      requestAnimationFrame(step);
    }
  };

  requestAnimationFrame(step);
}

function getGuideCopiesForStage(stageId) {
  if (stageId === "common-words") {
    return 2;
  }

  if (stageId === "phrases") {
    return 1;
  }

  return 6;
}

function buildReferenceSheet(text, mode = state.lessonMode) {
  const referenceSheet = document.querySelector("#reference-sheet");
  if (!referenceSheet) {
    return;
  }

  const guideCopies = getGuideCopiesForStage(route.stageId);
  const script = normalizeLessonMode(mode);

  referenceSheet.replaceChildren();
  referenceSheet.dataset.stageId = route.stageId || "";
  referenceSheet.dataset.script = script;
  referenceSheet.lang = script === LESSON_MODES.HARD ? "ru" : "en";
  referenceSheet.style.setProperty("--row-count", String(practice.rows));
  referenceSheet.classList.toggle("show-guides", practice.showGuides);

  for (let index = 0; index < practice.rows; index += 1) {
    const line = document.createElement("div");
    line.className = "practice-line";

    for (let copy = 0; copy < guideCopies; copy += 1) {
      const guide = document.createElement("span");
      guide.className = "letter-guide";
      guide.textContent = text;
      line.append(guide);
    }

    referenceSheet.append(line);
  }
}

function setupPracticeSurface() {
  destroyPracticeSurface();

  const canvas = document.querySelector("#practice-canvas");
  if (!canvas) {
    return;
  }

  practice.canvas = canvas;
  practice.ctx = canvas.getContext("2d");
  practice.strokes = [];
  practice.currentStroke = [];
  practice.isDrawing = false;
  practice.activePointerId = null;
  practice.activeTouchId = null;

  if (supportsPointerEvents) {
    canvas.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    return;
  }

  canvas.addEventListener("mousedown", handleMouseDown);
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", handleMouseUp);
  canvas.addEventListener("touchstart", handleTouchStart, { passive: false });
  canvas.addEventListener("touchmove", handleTouchMove, { passive: false });
  window.addEventListener("touchend", handleTouchEnd, { passive: false });
  window.addEventListener("touchcancel", handleTouchEnd, { passive: false });
}

function destroyPracticeSurface() {
  cancelStrokeRenderLoop();
  if (practice.canvas) {
    if (supportsPointerEvents) {
      practice.canvas.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    } else {
      practice.canvas.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      practice.canvas.removeEventListener("touchstart", handleTouchStart);
      practice.canvas.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
      window.removeEventListener("touchcancel", handleTouchEnd);
    }
  }

  practice.canvas = null;
  practice.ctx = null;
  practice.strokes = [];
  practice.currentStroke = [];
  practice.isDrawing = false;
  practice.pixelRatio = 1;
  practice.surfaceWidth = 0;
  practice.surfaceHeight = 0;
  practice.activePointerId = null;
  practice.activeTouchId = null;
  practice.inputPoint = null;
  practice.renderPoint = null;
}

function syncCanvasResolution() {
  if (!practice.canvas || !practice.ctx) {
    return;
  }

  const { width, height } = practice.canvas.getBoundingClientRect();
  if (width <= 0 || height <= 0) {
    return;
  }
  const ratio = window.devicePixelRatio || 1;
  const nextWidth = Math.max(1, Math.floor(width * ratio));
  const nextHeight = Math.max(1, Math.floor(height * ratio));

  if (practice.canvas.width !== nextWidth || practice.canvas.height !== nextHeight) {
    practice.canvas.width = nextWidth;
    practice.canvas.height = nextHeight;
  }

  practice.pixelRatio = ratio;
  practice.surfaceWidth = width;
  practice.surfaceHeight = height;
  practice.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  practice.ctx.lineCap = "round";
  practice.ctx.lineJoin = "round";
  practice.ctx.strokeStyle = "#fbbf24";
  practice.ctx.lineWidth = Math.max(2.75, 7.75 - practice.rows);
}

function redrawCanvas() {
  if (!practice.ctx || !practice.canvas) {
    return;
  }

  practice.ctx.setTransform(1, 0, 0, 1, 0, 0);
  practice.ctx.clearRect(0, 0, practice.canvas.width, practice.canvas.height);
  practice.ctx.setTransform(practice.pixelRatio, 0, 0, practice.pixelRatio, 0, 0);

  for (const stroke of practice.strokes) {
    drawStroke(stroke);
  }
  if (practice.currentStroke.length) {
    drawStroke(practice.currentStroke);
  }
}

function drawStroke(points) {
  if (!practice.ctx || points.length === 0) {
    return;
  }

  const ctx = practice.ctx;
  if (points.length === 1) {
    ctx.beginPath();
    ctx.fillStyle = ctx.strokeStyle;
    ctx.arc(points[0].x, points[0].y, ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }

  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  if (points.length === 2) {
    ctx.lineTo(points[1].x, points[1].y);
    ctx.stroke();
    return;
  }

  for (let index = 1; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    const midpointX = (current.x + next.x) / 2;
    const midpointY = (current.y + next.y) / 2;
    ctx.quadraticCurveTo(current.x, current.y, midpointX, midpointY);
  }

  const penultimate = points[points.length - 2];
  const last = points[points.length - 1];
  ctx.quadraticCurveTo(penultimate.x, penultimate.y, last.x, last.y);
  ctx.stroke();
}

function handlePointerDown(event) {
  if (!practice.canvas || event.button !== 0) {
    return;
  }

  event.preventDefault();
  if (typeof event.pointerId === "number") {
    practice.activePointerId = event.pointerId;
  }
  try {
    practice.canvas.setPointerCapture?.(event.pointerId);
  } catch {
    // Firefox can reject capture during rapid route or tab changes. Drawing still works without it.
  }
  startStroke(relativePoint(event));
}

function handlePointerMove(event) {
  if (!practice.isDrawing || !isActivePointerEvent(event)) {
    return;
  }
  extendStroke(relativePoint(event));
}

function handlePointerUp(event) {
  if (!practice.isDrawing || !isActivePointerEvent(event)) {
    return;
  }

  if (practice.canvas && typeof event?.pointerId === "number") {
    try {
      practice.canvas.releasePointerCapture?.(event.pointerId);
    } catch {
      // Ignore capture-release mismatches when pointer state changed outside this canvas.
    }
  }
  practice.activePointerId = null;
  finishStroke();
}

function handleMouseDown(event) {
  if (event.button !== 0) {
    return;
  }

  event.preventDefault();
  startStroke(relativePoint(event));
}

function handleMouseMove(event) {
  if (!practice.isDrawing) {
    return;
  }

  extendStroke(relativePoint(event));
}

function handleMouseUp() {
  finishStroke();
}

function handleTouchStart(event) {
  const touch = event.changedTouches[0];
  if (!touch) {
    return;
  }

  event.preventDefault();
  practice.activeTouchId = touch.identifier;
  startStroke(relativePoint(touch));
}

function handleTouchMove(event) {
  if (!practice.isDrawing) {
    return;
  }

  const touch = findTrackedTouch(event.changedTouches);
  if (!touch) {
    return;
  }

  event.preventDefault();
  extendStroke(relativePoint(touch));
}

function handleTouchEnd(event) {
  if (!practice.isDrawing) {
    return;
  }

  const touch = findTrackedTouch(event.changedTouches);
  if (!touch) {
    return;
  }

  event.preventDefault();
  practice.activeTouchId = null;
  finishStroke();
}

function startStroke(point) {
  if (practice.currentStroke.length) {
    appendStrokePoint(practice.inputPoint || practice.renderPoint || point, { force: true });
    finalizeStroke();
  }

  practice.isDrawing = true;
  practice.currentStroke = [point];
  practice.inputPoint = point;
  practice.renderPoint = point;
  practice.lastFrameTime = 0;
  redrawCanvas();
}

function extendStroke(point) {
  practice.inputPoint = point;
  ensureStrokeRenderLoop();
}

function finishStroke() {
  if (!practice.isDrawing) {
    return;
  }

  practice.isDrawing = false;
  ensureStrokeRenderLoop();
}

function isActivePointerEvent(event) {
  return practice.activePointerId === null || event.pointerId === practice.activePointerId;
}

function findTrackedTouch(touchList) {
  for (let index = 0; index < touchList.length; index += 1) {
    const touch = touchList[index];
    if (touch.identifier === practice.activeTouchId) {
      return touch;
    }
  }
  return null;
}

function clearCanvas() {
  cancelStrokeRenderLoop();
  practice.isDrawing = false;
  practice.strokes = [];
  practice.currentStroke = [];
  practice.inputPoint = null;
  practice.renderPoint = null;
  redrawCanvas();
}

function toggleGuides() {
  practice.showGuides = !practice.showGuides;
  const referenceSheet = document.querySelector("#reference-sheet");
  referenceSheet?.classList.toggle("show-guides", practice.showGuides);
  updateLessonButtons();
}

function updateLessonButtons() {
  const toggleButton = document.querySelector("#toggle-guides-button");
  const rowsLabel = document.querySelector("#rows-label");
  const decreaseButton = document.querySelector("#decrease-rows-button");
  const increaseButton = document.querySelector("#increase-rows-button");
  if (toggleButton) {
    toggleButton.textContent = `${practice.showGuides ? "✓ " : ""}Guides`;
  }
  if (rowsLabel) {
    rowsLabel.textContent = `${practice.rows} ${rowsNoun(practice.rows)}`;
  }
  if (decreaseButton) {
    decreaseButton.disabled = practice.rows <= 2;
  }
  if (increaseButton) {
    increaseButton.disabled = practice.rows >= 6;
  }
}

function changeRows(delta) {
  const next = Math.max(2, Math.min(6, practice.rows + delta));
  if (next === practice.rows) {
    return;
  }
  practice.rows = next;
  if (route.view === "lesson") {
    const lesson = getLessonForRoute(route.stageId, route.lessonId);
    if (lesson) {
      buildReferenceSheet(getLessonText(lesson, state.lessonMode), state.lessonMode);
      scheduleLessonRefresh();
      updateLessonButtons();
    }
  }
}

function handleCreateProfile(event) {
  event.preventDefault();
  if (state.profiles.length >= MAX_PROFILES) {
    window.alert(`Maximum profiles: ${MAX_PROFILES}.`);
    return;
  }

  const formData = new FormData(form);
  const name = String(formData.get("profileName") || "").trim();
  const practiceNameEasy = String(formData.get("practiceNameEasy") || "").trim();
  const practiceNameHard = String(formData.get("practiceNameHard") || "").trim();
  const avatar = String(formData.get("avatar") || "A").trim();

  if (!name) {
    window.alert("Enter a name.");
    return;
  }

  const profile = createProfileRecord({ name, practiceNameEasy, practiceNameHard, avatar });
  state.profiles.push(profile);
  state.activeProfileId = profile.id;
  saveState(state);
  form.reset();
  closeProfileDialog();
  navigateToStages();
}

function openProfileDialog() {
  if (state.profiles.length >= MAX_PROFILES) {
    window.alert(`Maximum profiles: ${MAX_PROFILES}.`);
    return;
  }

  document.body.classList.add("dialog-open");
  if (supportsDialog) {
    dialog.showModal();
    return;
  }

  dialog.setAttribute("open", "");
}

function closeProfileDialog() {
  document.body.classList.remove("dialog-open");
  if (!dialog?.hasAttribute("open")) {
    return;
  }

  if (typeof dialog.close === "function") {
    dialog.close();
    return;
  }

  dialog.removeAttribute("open");
}

function profileProgressLabel(profile) {
  const easyCompleted = countCompletedLessons(profile, LESSON_MODES.EASY);
  const hardCompleted = countCompletedLessons(profile, LESSON_MODES.HARD);
  return `Easy ${easyCompleted}/${TOTAL_LESSONS_PER_MODE} · Hard ${hardCompleted}/${TOTAL_LESSONS_PER_MODE}`;
}

function getActiveProfile() {
  return state.profiles.find((profile) => profile.id === state.activeProfileId) || null;
}

function countCompletedLessons(profile, mode) {
  return stages.reduce((total, stage) => {
    const completed = stage.lessons.filter((lesson) => isLessonCompleteForMode(profile, lesson.id, mode)).length;
    return total + completed;
  }, 0);
}

function isLessonCompleteForMode(profile, lessonId, mode) {
  return Boolean(profile.progress?.[makeProgressKey(normalizeLessonMode(mode), lessonId)]?.completed);
}

function isLessonComplete(profile, lessonId) {
  return isLessonCompleteForMode(profile, lessonId, state.lessonMode);
}

function markLessonComplete(profile, lessonId) {
  if (route.stageId === "custom") {
    return;
  }
  profile.progress[makeProgressKey(state.lessonMode, lessonId)] = {
    completed: true,
    completedAt: Date.now(),
  };
  saveState(state);
}

function getNextLesson(stageId, lessonId) {
  if (stageId === "custom") {
    return null;
  }
  const stage = stages.find((entry) => entry.id === stageId);
  if (!stage) {
    return null;
  }
  const currentIndex = stage.lessons.findIndex((lesson) => lesson.id === lessonId);
  if (currentIndex === -1 || currentIndex === stage.lessons.length - 1) {
    return null;
  }
  return stage.lessons[currentIndex + 1];
}

function navigateToProfiles() {
  window.location.hash = "profiles";
}

function navigateToStages() {
  window.location.hash = "stages";
}

function navigateToLesson(stageId, lessonId) {
  window.location.hash = `lesson/${encodeURIComponent(stageId)}/${encodeURIComponent(lessonId)}`;
}

function openLesson(customLessonId) {
  navigateToLesson("custom", customLessonId);
}

function getCustomPracticeText(profile, mode) {
  if (!profile) {
    return "";
  }

  if (normalizeLessonMode(mode) === LESSON_MODES.HARD) {
    return String(profile.practiceNameHard || "").trim();
  }

  return String(profile.practiceNameEasy || profile.name || "").trim();
}

function buildCustomNameLesson(profile) {
  return {
    id: "custom-name",
    text: {
      easy: getCustomPracticeText(profile, LESSON_MODES.EASY),
      hard: getCustomPracticeText(profile, LESSON_MODES.HARD),
    },
  };
}

function relativePoint(event) {
  if (!practice.canvas) {
    return { x: 0, y: 0 };
  }
  const rect = practice.canvas.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

function ensureStrokeRenderLoop() {
  if (practice.strokeFrameId !== null) {
    return;
  }

  practice.strokeFrameId = requestAnimationFrame(renderStrokeFrame);
}

function cancelStrokeRenderLoop() {
  if (practice.strokeFrameId !== null) {
    cancelAnimationFrame(practice.strokeFrameId);
    practice.strokeFrameId = null;
  }
  practice.lastFrameTime = 0;
}

function renderStrokeFrame(timestamp) {
  practice.strokeFrameId = null;
  if (!practice.currentStroke.length || !practice.inputPoint || !practice.renderPoint) {
    practice.lastFrameTime = 0;
    redrawCanvas();
    return;
  }

  const elapsedMs = practice.lastFrameTime ? Math.min(34, Math.max(8, timestamp - practice.lastFrameTime)) : 16;
  practice.lastFrameTime = timestamp;

  const followStrength = practice.isDrawing
    ? STROKE_RENDER.followStrength
    : STROKE_RENDER.followStrength * STROKE_RENDER.releaseFollowBoost;

  practice.renderPoint = easePoint(practice.renderPoint, practice.inputPoint, followStrength, elapsedMs);
  appendStrokePoint(practice.renderPoint);

  const remainingDistance = pointDistance(practice.renderPoint, practice.inputPoint);
  if (!practice.isDrawing && remainingDistance <= STROKE_RENDER.settleDistance) {
    appendStrokePoint(practice.inputPoint, { force: true });
    finalizeStroke();
    return;
  }

  redrawCanvas();

  if (remainingDistance > STROKE_RENDER.settleDistance) {
    ensureStrokeRenderLoop();
    return;
  }

  practice.lastFrameTime = 0;
}

function appendStrokePoint(point, { force = false } = {}) {
  if (!practice.currentStroke.length) {
    practice.currentStroke = [point];
    return;
  }

  const lastPoint = practice.currentStroke[practice.currentStroke.length - 1];
  const distance = pointDistance(lastPoint, point);
  if (!force && distance < STROKE_RENDER.minPointDistance) {
    return;
  }

  const steps = Math.max(1, Math.ceil(distance / STROKE_RENDER.maxSegmentLength));
  for (let step = 1; step <= steps; step += 1) {
    const nextPoint = interpolatePoint(lastPoint, point, step / steps);
    const previousPoint = practice.currentStroke[practice.currentStroke.length - 1];
    const gap = pointDistance(previousPoint, nextPoint);
    if ((force && gap > 0.01) || (!force && (gap >= STROKE_RENDER.minPointDistance || step === steps))) {
      practice.currentStroke.push(nextPoint);
    }
  }
}

function finalizeStroke() {
  cancelStrokeRenderLoop();
  if (practice.currentStroke.length > 1) {
    practice.strokes.push([...practice.currentStroke]);
  }
  practice.currentStroke = [];
  practice.inputPoint = null;
  practice.renderPoint = null;
  practice.isDrawing = false;
  redrawCanvas();
}

function easePoint(from, to, followStrength, elapsedMs) {
  const progress = 1 - Math.exp((-followStrength * elapsedMs) / 1000);
  return interpolatePoint(from, to, progress);
}

function interpolatePoint(from, to, progress) {
  return {
    x: from.x + (to.x - from.x) * progress,
    y: from.y + (to.y - from.y) * progress,
  };
}

function pointDistance(from, to) {
  const deltaX = to.x - from.x;
  const deltaY = to.y - from.y;
  return Math.hypot(deltaX, deltaY);
}

function getLessonForRoute(stageId, lessonId) {
  if (stageId === "custom") {
    if (lessonId !== "custom-name") {
      return null;
    }

    const profile = getActiveProfile();
    return profile ? buildCustomNameLesson(profile) : null;
  }
  return getCurriculumLesson(stageId, lessonId);
}

function setLessonMode(enabled) {
  document.body.classList.toggle("lesson-mode", enabled);
}

function rowsNoun(count) {
  return count === 1 ? "row" : "rows";
}
