(() => {
  const curriculum = globalThis.CursiveCurriculum;
  if (!curriculum) {
    throw new Error("CursiveCurriculum must load before storage.js.");
  }

  const STORAGE_KEY = "learn-russian-cursive";
  const STORAGE_VERSION = 3;

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return defaultState();
      }

      const parsed = JSON.parse(raw);
      return {
        version: STORAGE_VERSION,
        activeProfileId: parsed.activeProfileId || null,
        profiles: Array.isArray(parsed.profiles) ? parsed.profiles.map(normalizeProfileRecord) : [],
      };
    } catch (error) {
      console.error("Failed to load cursive app state.", error);
      return defaultState();
    }
  }

  function saveState(state) {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: STORAGE_VERSION,
          activeProfileId: state.activeProfileId || null,
          profiles: Array.isArray(state.profiles) ? state.profiles.map(normalizeProfileRecord) : [],
        }),
      );
    } catch (error) {
      console.error("Failed to save cursive app state.", error);
    }
  }

  function defaultState() {
    return {
      version: STORAGE_VERSION,
      activeProfileId: null,
      profiles: [],
    };
  }

  function createProfileRecord({ name, practiceName, avatar }) {
    return normalizeProfileRecord({
      id: globalThis.crypto?.randomUUID?.() || String(Date.now()),
      name,
      practiceName,
      avatar,
      createdAt: Date.now(),
      progress: {},
    });
  }

  function makeProgressKey(lessonId) {
    return String(lessonId || "").trim();
  }

  function normalizeProfileRecord(profile = {}) {
    const name = String(profile.name || "").trim();
    const avatar = String(profile.avatar || deriveAvatar(name)).trim() || deriveAvatar(name);
    const practiceName = String(
      profile.practiceName || profile.practiceNameHard || profile.practiceNameEasy || name,
    ).trim();

    return {
      id: profile.id || globalThis.crypto?.randomUUID?.() || String(Date.now()),
      name,
      practiceName,
      avatar,
      createdAt: Number(profile.createdAt) || Date.now(),
      progress: normalizeProgressRecord(profile.progress),
    };
  }

  function deriveAvatar(name) {
    const initial = String(name || "").trim().charAt(0).toUpperCase();
    return initial || "A";
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

      const lessonId = normalizeLegacyProgressKey(key);
      if (!lessonId) {
        continue;
      }

      const completedAt = Number(value.completedAt) || Date.now();
      const existing = nextProgress[lessonId];

      nextProgress[lessonId] = {
        completed: Boolean(existing?.completed || value.completed),
        completedAt: Math.max(Number(existing?.completedAt) || 0, completedAt),
      };
    }

    return nextProgress;
  }

  function normalizeLegacyProgressKey(key) {
    const normalizedKey = String(key || "").trim();
    if (!normalizedKey) {
      return "";
    }

    if (normalizedKey.startsWith("easy:") || normalizedKey.startsWith("hard:")) {
      return normalizedKey.slice(normalizedKey.indexOf(":") + 1);
    }

    return normalizedKey;
  }

  globalThis.CursiveStorage = Object.freeze({
    createProfileRecord,
    defaultState,
    loadState,
    makeProgressKey,
    saveState,
  });
})();
