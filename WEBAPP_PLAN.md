# Photon Web App — Full Plan (Streamlit + Streamlit Community Cloud)

Цель: получить рабочий **Demo Application URL** для формы сабмишена, показав живой
веб-апп в цветах лого — **не меняя код агента**.

---

## 0. Как это ложится в форму сабмишена

| Поле формы | Что вписать |
|---|---|
| GitHub Repository | `https://github.com/theinlao1/photon-video-captioner` (уже есть) |
| Demo Application Platform | **Streamlit** (или "Web") |
| Demo Application URL | `https://<...>.streamlit.app` — появится после деплоя (шаг 4) |
| Docker Image | образ агента `ghcr.io/<...>:tag` — это ОТДЕЛЬНАЯ вещь, к веб-аппу не относится |

Ключевая мысль: **судит Track 2 по Docker-образу**, а веб-апп нужен только чтобы
заполнить обязательное поле Demo URL и красиво показать проект. Поэтому веб-апп
не должен рисковать кодом агента.

## 1. Принцип «не ломаем агента»

- Веб-апп — **новая точка входа** `streamlit_app.py` в корне репо. Он только
  `import`-ит существующие модули `app/frames.py` и `app/captioner.py`.
- Ни один файл агента (`app/main.py`, `Dockerfile`, `app/*.py`) **не меняется**.
- У веб-аппа **свои** зависимости (`requirements_webapp.txt`) — на Streamlit Cloud
  они не конфликтуют с агентским `requirements.txt`.
- Секреты (ключи) — через **Streamlit secrets**, не через git.

Почему импорт безопасен: `llm_client.py` читает `PRIMARY_*/FALLBACK_*` из
`os.environ` в момент вызова. Веб-апп кладёт значения из `st.secrets` в `os.environ`
до вызова пайплайна — и `extract_frames()` + `caption_video()` работают как есть.

## 2. Гибрид-демо (как договорились)

- **Вкладка «Examples»** — 3 примера клипа с уже готовыми подписями из
  `examples_results.json` (реальный вывод нашего прогона). Грузится мгновенно,
  показывает и видео, и 4 стиля. Всегда работает, даже если API лежит.
- **Вкладка «Try your own»** — поле для URL → кнопка → живой прогон настоящего
  пайплайна (`extract_frames` → `caption_video`) → 4 карточки стилей.
  Включается только если в secrets есть ключ; иначе показывает подсказку.

## 3. Файлы, которые ДОБАВЛЯЕМ в репо `photon-video-captioner`

Скопировать из этой папки `webapp/` в **корень** репо агента:

```
photon-video-captioner/
├── app/                      # (существует, НЕ трогаем)
├── Dockerfile                # (существует, НЕ трогаем)
├── requirements.txt          # (существует, агентский — НЕ трогаем)
├── streamlit_app.py          # ← НОВОЕ (главный файл веб-аппа)
├── requirements_webapp.txt   # ← НОВОЕ (деп-ы веб-аппа)
├── packages.txt              # ← НОВОЕ (ffmpeg для хоста)
├── examples_results.json     # ← НОВОЕ (готовые примеры)
├── .streamlit/
│   └── config.toml           # ← НОВОЕ (тёмная тема в цветах лого)
└── assets/
    └── photon_logo.png       # ← ПОЛОЖИ сюда логотип
```

Важно про requirements на Streamlit Cloud: облако ставит из файла
`requirements.txt`. Есть два варианта — выбери один:
- **(A, проще)** переименуй `requirements_webapp.txt` → и слей его содержимое в
  агентский `requirements.txt` (добавив `streamlit`, `python-dotenv`). Ничего в
  логике агента не ломается — это просто доп. пакеты в образе.
- **(B, чище)** в настройках Streamlit-приложения укажи путь к
  `requirements_webapp.txt` как отдельному файлу зависимостей (Advanced settings).

`packages.txt` в корне Streamlit Cloud подхватывает автоматически (ставит `ffmpeg`).

## 4. Деплой на Streamlit Community Cloud (пошагово)

1. Залей добавленные файлы в GitHub (в тот же репо, ветка main).
2. Зайди на **share.streamlit.io** → Sign in with GitHub → **New app**.
3. Repository: `theinlao1/photon-video-captioner`, Branch: `main`,
   Main file path: `streamlit_app.py`.
4. **Advanced settings → Secrets**: вставь содержимое `secrets.template.toml`
   с реальными ключами (лучше **disposable-ключ с дневным лимитом**).
5. Deploy. Через пару минут получишь URL `https://<...>.streamlit.app`.
6. Открой URL, проверь: вкладка Examples грузится мгновенно; вкладка Try your own
   на тестовом mp4 отдаёт 4 стиля за ~30–60с.
7. Этот URL → в поле **Demo Application URL** формы.

## 5. Риски и как их закрыть

- **ffmpeg на хосте** → уже решено `packages.txt` (ставит ffmpeg на Streamlit Cloud).
- **Ключ на публичном хосте** → используем disposable-ключ с жёстким лимитом трат;
  живой режим можно вообще выключить (убрать ключ из secrets) — тогда останутся
  только Examples, и Demo URL всё равно валиден.
- **UHD-клипы долгие/таймаут** → в живом режиме подписываем «~30–60с»; фолбэки
  пайплайна и так отдадут результат. Для демо лучше короткие клипы.
- **Холодный старт Streamlit** (засыпает без трафика) → первый заход может грузиться
  ~30с; для жюри это нормально, можно разок «разбудить» перед проверкой.
- **Не сломать агента** → мы только добавляем файлы; агентские `main.py`/`Dockerfile`
  остаются нетронутыми, сабмишен Track 2 (Docker-образ) от этого не зависит.

## 6. Чеклист для Claude Code (выполнять в репо агента)

1. Скопировать файлы из `webapp/` в корень репо (см. дерево в п.3).
2. Положить логотип в `assets/photon_logo.png`.
3. Слить зависимости: добавить `streamlit`, `python-dotenv` в `requirements.txt`
   (вариант A) — не трогая остальное.
4. Локально проверить: `streamlit run streamlit_app.py` (с `.streamlit/secrets.toml`
   локально, который в `.gitignore`).
5. Убедиться, что `.env` и `secrets.toml` в `.gitignore` (ключи не в git!).
6. Запушить в main → задеплоить на Streamlit Cloud (п.4) → вписать secrets.
7. Скопировать выданный `.streamlit.app` URL в форму сабмишена.

Готово: агент не тронут, демо живое и в цветах Photon, поле Demo URL закрыто.
