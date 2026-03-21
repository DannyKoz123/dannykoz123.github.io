import { DEFAULT_LESSON_MODE, LESSON_MODES } from "./curriculum.js";

const STORAGE_KEY = "learn-russian-cursive";
const STORAGE_VERSION = 2;

export function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return defaultState();
    }

    const parsed = JSON.parse(raw);
    return {
      version: STORAGE_VERSION,
      activeProfileId: parsed.activeProfileId || null,
      lessonMode: normalizeLessonMode(parsed.lessonMode),
      profiles: Array.isArray(parsed.profiles) ? parsed.profiles.map(normalizeProfileRecord) : [],
    };
  } catch (error) {
    console.error("Failed to load cursive app state.", error);
    return defaultState();
  }
}

export function saveState(state) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      version: STORAGE_VERSION,
      activeProfileId: state.activeProfileId || null,
      lessonMode: normalizeLessonMode(state.lessonMode),
      profiles: Array.isArray(state.profiles) ? state.profiles.map(normalizeProfileRecord) : [],
    }),
  );
}

export function defaultState() {
  return {
    version: STORAGE_VERSION,
    activeProfileId: null,
    lessonMode: DEFAULT_LESSON_MODE,
    profiles: [],
  };
}

export function createProfileRecord({ name, practiceNameEasy, practiceNameHard, avatar }) {
  return normalizeProfileRecord({
    id: globalThis.crypto?.randomUUID?.() || String(Date.now()),
    name,
    practiceNameEasy,
    practiceNameHard,
    avatar,
    createdAt: Date.now(),
    progress: {},
  });
}

export function makeProgressKey(mode, lessonId) {
  return `${normalizeLessonMode(mode)}:${lessonId}`;
}

function normalizeProfileRecord(profile = {}) {
  return {
    id: profile.id || globalThis.crypto?.randomUUID?.() || String(Date.now()),
    name: String(profile.name || "").trim(),
    practiceNameEasy: String(profile.practiceNameEasy || profile.name || "").trim(),
    practiceNameHard: String(profile.practiceNameHard || profile.practiceName || "").trim(),
    avatar: String(profile.avatar || "A").trim() || "A",
    createdAt: Number(profile.createdAt) || Date.now(),
    progress: normalizeProgressRecord(profile.progress),
  };
}

function normalizeProgressRecord(progress) {
  if (!progress || typeof progress !== "object") {
    return {};
  }

  const nextProgress = {};

  for (const [key, value] of Object.entries(progress)) {
    if (!value || typeof value !== "object") {
      continue;
    }

    if (key.startsWith(`${LESSON_MODES.EASY}:`) || key.startsWith(`${LESSON_MODES.HARD}:`)) {
      nextProgress[key] = {
        completed: Boolean(value.completed),
        completedAt: Number(value.completedAt) || Date.now(),
      };
      continue;
    }

    nextProgress[makeProgressKey(LESSON_MODES.HARD, key)] = {
      completed: Boolean(value.completed),
      completedAt: Number(value.completedAt) || Date.now(),
    };
  }

  return nextProgress;
}

function normalizeLessonMode(mode) {
  return mode === LESSON_MODES.HARD ? LESSON_MODES.HARD : DEFAULT_LESSON_MODE;
}
