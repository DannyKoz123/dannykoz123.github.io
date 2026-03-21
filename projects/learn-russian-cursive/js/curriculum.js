export const LESSON_MODES = {
  EASY: "easy",
  HARD: "hard",
};

export const DEFAULT_LESSON_MODE = LESSON_MODES.EASY;

export const MODE_LABELS = {
  [LESSON_MODES.EASY]: "Easy",
  [LESSON_MODES.HARD]: "Hard",
};

export const MODE_LANGUAGE_LABELS = {
  [LESSON_MODES.EASY]: "English",
  [LESSON_MODES.HARD]: "Russian",
};

export const stages = [
  {
    id: "lowercase-strokes",
    order: 1,
    name: "Lowercase Strokes",
    sample: {
      easy: "i l m n a o",
      hard: "ии шш лл мм",
    },
    lessons: [
      makeLesson("lower-и", "i", "и"),
      makeLesson("lower-ш", "l", "ш"),
      makeLesson("lower-л", "m", "л"),
      makeLesson("lower-м", "n", "м"),
      makeLesson("lower-а", "a", "а"),
      makeLesson("lower-о", "o", "о"),
    ],
  },
  {
    id: "joins-and-syllables",
    order: 2,
    name: "Joins",
    sample: {
      easy: "li ll mi lo th ri",
      hard: "ма мо ми ли ши ро",
    },
    lessons: [
      makeLesson("join-ма", "li", "ма"),
      makeLesson("join-ло", "ll", "ло"),
      makeLesson("join-ши", "mi", "ши"),
      makeLesson("join-ми", "lo", "ми"),
      makeLesson("join-ро", "th", "ро"),
      makeLesson("join-уж", "ri", "уж"),
    ],
  },
  {
    id: "common-words",
    order: 3,
    name: "Words",
    sample: {
      easy: "mama home school book",
      hard: "мама дом школа книга",
    },
    lessons: [
      makeLesson("word-мама", "mama", "мама"),
      makeLesson("word-дом", "home", "дом"),
      makeLesson("word-школа", "school", "школа"),
      makeLesson("word-книга", "book", "книга"),
      makeLesson("word-река", "river", "река"),
      makeLesson("word-улица", "street", "улица"),
    ],
  },
  {
    id: "uppercase-forms",
    order: 4,
    name: "Uppercase Forms",
    sample: {
      easy: "A L M D Y J",
      hard: "А Л М Д Я Ю",
    },
    lessons: [
      makeLesson("upper-А", "A", "А"),
      makeLesson("upper-Л", "L", "Л"),
      makeLesson("upper-М", "M", "М"),
      makeLesson("upper-Д", "D", "Д"),
      makeLesson("upper-Я", "Y", "Я"),
      makeLesson("upper-Ю", "J", "Ю"),
    ],
  },
  {
    id: "phrases",
    order: 5,
    name: "Phrases",
    sample: {
      easy: "Moscow, coffee, Scotland",
      hard: "Москва, кофе, Шотландия",
    },
    lessons: [
      makeLesson(
        "phrase-moscow-london",
        "Moscow is more beautiful than London",
        "Москва красивее, чем Лондон",
      ),
      makeLesson(
        "phrase-adams-brother",
        "Adam's brother loves Moscow",
        "Брат Адама любит Москву",
      ),
      makeLesson(
        "phrase-coffee",
        "Coffee with milk and sugar",
        "Кофе с молоком и с сахаром",
      ),
      makeLesson(
        "phrase-scotland",
        "Scotland's lakes and mountains are very beautiful",
        "Озера и горы Шотландии очень красивые",
      ),
      makeLesson(
        "phrase-smart",
        "She is beautiful and smart",
        "Она и красива и умна",
      ),
      makeLesson(
        "phrase-grandmother",
        "Our grandmother usually goes to the store in the morning",
        "Наша бабушка обычно ходит в магазин утром",
      ),
    ],
  },
];

export const MAX_PROFILES = 4;
export const TOTAL_LESSONS_PER_MODE = stages.reduce((sum, stage) => sum + stage.lessons.length, 0);

export function getStage(stageId) {
  return stages.find((stage) => stage.id === stageId) || null;
}

export function getLesson(stageId, lessonId) {
  const stage = getStage(stageId);
  return stage?.lessons.find((lesson) => lesson.id === lessonId) || null;
}

export function getLessonById(lessonId) {
  for (const stage of stages) {
    const lesson = stage.lessons.find((entry) => entry.id === lessonId);
    if (lesson) {
      return { stage, lesson };
    }
  }
  return null;
}

export function getStageSample(stage, mode = DEFAULT_LESSON_MODE) {
  return stage?.sample?.[mode] || stage?.sample?.[DEFAULT_LESSON_MODE] || "";
}

export function getLessonText(lesson, mode = DEFAULT_LESSON_MODE) {
  if (!lesson) {
    return "";
  }

  if (typeof lesson.text === "string") {
    return lesson.text;
  }

  return lesson.text?.[mode] || lesson.text?.[DEFAULT_LESSON_MODE] || "";
}

function makeLesson(id, easyText, hardText) {
  return {
    id,
    text: {
      easy: easyText,
      hard: hardText,
    },
  };
}
