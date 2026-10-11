// Replace this adapter with your backend implementation. UI depends only on this interface.
export const api = {
  mode: 'demo',
  // No mock account creation: replace this with a real backend registration request.
  async register({email,name,password,role}) {
    const error = new Error('Account registration backend is not connected');
    error.code = 'AUTH_NOT_CONFIGURED';
    throw error;
  },
  async getQuestions(config) {
    await new Promise(r => setTimeout(r, 650));
    return [
      'Какую главную мысль слушатель должен запомнить после вашего выступления?',
      'Какой пример или факт лучше всего подтверждает вашу позицию?',
      'Какой следующий шаг вы предлагаете аудитории?'
    ];
  },
  async analyze({ config, recording, segments }) {
    if (!recording || recording.size === 0) throw new Error('Запись не сохранилась. Вернитесь к проверке устройств и повторите тренировку.');
    await new Promise(r => setTimeout(r, 1800));
    return demoResult(config.questions);
  }
};
export function demoResult(withQuestions = false) {
  return {
    demo: true,
    insight: 'Сильное выступление строится вокруг одной главной мысли. Подкрепите её конкретным примером и завершите понятным выводом.',
    metrics: [
      { title: 'Темп речи', text: 'Пример: ровный темп с короткими паузами после важных мыслей.', label: 'Темп' },
      { title: 'Структура', text: 'Пример: вступление → основная мысль → аргумент → вывод.', label: 'Структура' },
      { title: 'Чистота речи', text: 'Пример: пауза помогает заменить слова «эээ» и «ну».', label: 'Речь' },
      ...(withQuestions ? [{ title: 'Ответы', text: 'Пример: сначала прямой ответ, затем короткое пояснение.', label: 'Диалог' }] : [])
    ],
    strengths: [
      { title: 'Одна понятная мысль', text: 'Пример сильной стороны: слушателю легко понять, что вы хотите сказать.' },
      { title: 'Конкретные примеры', text: 'Пример сильной стороны: аргументы связаны с понятными ситуациями.' },
      { title: 'Контакт с аудиторией', text: 'Пример сильной стороны: паузы дают слушателям время осмыслить сказанное.' }
    ],
    recommendations: [
      { title: 'Сформулируйте главное в одной фразе', text: 'До начала выступления запишите: «После моего выступления аудитория должна понять…».' },
      { title: 'Добавьте один убедительный пример', text: 'Выберите случай, цифру или короткую историю, которые подтверждают главную мысль.' },
      { title: 'Закончите выводом', text: 'В последних двух предложениях повторите главное и предложите следующий шаг.' }
    ]
  };
}
