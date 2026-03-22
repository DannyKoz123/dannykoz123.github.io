(() => {
  const RUSSIAN_ALPHABET = [
    { lowercase: "а", uppercase: "А" },
    { lowercase: "б", uppercase: "Б" },
    { lowercase: "в", uppercase: "В" },
    { lowercase: "г", uppercase: "Г" },
    { lowercase: "д", uppercase: "Д" },
    { lowercase: "е", uppercase: "Е" },
    { lowercase: "ё", uppercase: "Ё" },
    { lowercase: "ж", uppercase: "Ж" },
    { lowercase: "з", uppercase: "З" },
    { lowercase: "и", uppercase: "И" },
    { lowercase: "й", uppercase: "Й" },
    { lowercase: "к", uppercase: "К" },
    { lowercase: "л", uppercase: "Л" },
    { lowercase: "м", uppercase: "М" },
    { lowercase: "н", uppercase: "Н" },
    { lowercase: "о", uppercase: "О" },
    { lowercase: "п", uppercase: "П" },
    { lowercase: "р", uppercase: "Р" },
    { lowercase: "с", uppercase: "С" },
    { lowercase: "т", uppercase: "Т" },
    { lowercase: "у", uppercase: "У" },
    { lowercase: "ф", uppercase: "Ф" },
    { lowercase: "х", uppercase: "Х" },
    { lowercase: "ц", uppercase: "Ц" },
    { lowercase: "ч", uppercase: "Ч" },
    { lowercase: "ш", uppercase: "Ш" },
    { lowercase: "щ", uppercase: "Щ" },
    { lowercase: "ъ", uppercase: "Ъ" },
    { lowercase: "ы", uppercase: "Ы" },
    { lowercase: "ь", uppercase: "Ь" },
    { lowercase: "э", uppercase: "Э" },
    { lowercase: "ю", uppercase: "Ю" },
    { lowercase: "я", uppercase: "Я" },
  ];

  const stages = [
    {
      id: "lowercase-strokes",
      order: 1,
      name: "Lowercase Letters",
      sample: "а б в г д",
      lessons: RUSSIAN_ALPHABET.map(({ lowercase }) => makeLesson(`lower-${lowercase}`, lowercase)),
    },
    {
      id: "joins-and-syllables",
      order: 2,
      name: "Joins",
      sample: "ма ло ши ми ро уж",
      lessons: [
        makeLesson("join-ма", "ма"),
        makeLesson("join-ло", "ло"),
        makeLesson("join-ши", "ши"),
        makeLesson("join-ми", "ми"),
        makeLesson("join-ро", "ро"),
        makeLesson("join-уж", "уж"),
      ],
    },
    {
      id: "common-words",
      order: 3,
      name: "Words",
      sample: "мама дом школа книга",
      lessons: [
        makeLesson("word-мама", "мама"),
        makeLesson("word-дом", "дом"),
        makeLesson("word-школа", "школа"),
        makeLesson("word-книга", "книга"),
        makeLesson("word-река", "река"),
        makeLesson("word-улица", "улица"),
      ],
    },
    {
      id: "uppercase-forms",
      order: 4,
      name: "Capital Letters",
      sample: "А Б В Г Д",
      lessons: RUSSIAN_ALPHABET.map(({ uppercase }) => makeLesson(`upper-${uppercase}`, uppercase)),
    },
    {
      id: "phrases",
      order: 5,
      name: "Phrases",
      sample: "Москва, кофе, Шотландия",
      lessons: [
        makeLesson("phrase-moscow-london", "Москва красивее, чем Лондон"),
        makeLesson("phrase-adams-brother", "Брат Адама любит Москву"),
        makeLesson("phrase-coffee", "Кофе с молоком и с сахаром"),
        makeLesson("phrase-scotland", "Озера и горы Шотландии очень красивые"),
        makeLesson("phrase-smart", "Она и красива и умна"),
        makeLesson("phrase-grandmother", "Наша бабушка обычно ходит в магазин утром"),
      ],
    },
  ];

  const MAX_PROFILES = 4;
  const TOTAL_LESSONS = stages.reduce((sum, stage) => sum + stage.lessons.length, 0);

  function getStage(stageId) {
    return stages.find((stage) => stage.id === stageId) || null;
  }

  function getLesson(stageId, lessonId) {
    const stage = getStage(stageId);
    return stage ? stage.lessons.find((lesson) => lesson.id === lessonId) || null : null;
  }

  function getLessonById(lessonId) {
    for (const stage of stages) {
      const lesson = stage.lessons.find((entry) => entry.id === lessonId);
      if (lesson) {
        return { stage, lesson };
      }
    }
    return null;
  }

  function getStageSample(stage) {
    return stage ? stage.sample || "" : "";
  }

  function getLessonText(lesson) {
    if (!lesson) {
      return "";
    }

    return typeof lesson.text === "string" ? lesson.text : "";
  }

  function makeLesson(id, text) {
    return { id, text };
  }

  globalThis.CursiveCurriculum = Object.freeze({
    MAX_PROFILES,
    TOTAL_LESSONS,
    getLesson,
    getLessonById,
    getLessonText,
    getStage,
    getStageSample,
    stages,
  });
})();
