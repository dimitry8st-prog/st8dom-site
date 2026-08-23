# Портфолио Дмитрия Степанова

Сайт AI-архитектора для бизнеса: диагностика процесса, MVP, RAG, Telegram-боты и автоматизация. Живой ориентир по содержанию и визуалу — [st8dom.ru](https://st8dom.ru/). Этот репозиторий — Flask-версия с формой заявок, кейсами и админкой.

Главная цель сайта — квалифицированные обращения на аудит, MVP и внедрение. Основной призыв ведёт в форму и в личный Telegram [@dimitry8st](https://t.me/dimitry8st), не в канал.

## Стек

- Python 3.11+
- Flask, Jinja2
- Flask-SQLAlchemy (SQLite)
- Flask-Login, Flask-WTF (CSRF и валидация)
- собственная CSS-система сайта (тёмная тема st8dom.ru)

Bootstrap сознательно не подключался: он сломал бы уже работающий визуал.

## Локальный запуск

```bash
python -m venv .venv
# Windows Git Bash:
source .venv/Scripts/activate
# Windows cmd: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
# или: cp .env.example .env
```

Заполните в `.env` как минимум `SECRET_KEY` и `ADMIN_PASSWORD`. Затем:

```bash
python app.py
```

Откройте http://127.0.0.1:5000/

Админка: http://127.0.0.1:5000/admin/login/  
Логин и пароль — из `.env` (`ADMIN_USERNAME`, `ADMIN_PASSWORD`). Пользователь создаётся при первом запуске, если таблица пустая.

## Команды

```bash
pip install -r requirements.txt
python -m pytest -q
python app.py
```

Отдельного lint/typecheck в проекте нет: это небольшое Jinja/Flask-приложение без mypy-конфига.

Production:

```bash
set FLASK_ENV=production
python app.py
```

На сервере используйте gunicorn (уже в `requirements.txt`):

```bash
set FLASK_ENV=production
gunicorn wsgi:app --bind 0.0.0.0:8000
```

## Переменные окружения

| Имя | Назначение |
| --- | --- |
| `SECRET_KEY` | Сессии и CSRF. Обязательно сменить вне localhost. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Первый администратор |
| `SITE_URL` | Canonical, Open Graph, sitemap |
| `DATABASE_URL` | По умолчанию SQLite `instance/site.db` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Копия заявки в Telegram |
| `ANALYTICS_ID` | Точка подключения аналитики |
| `FLASK_ENV` | `development` или `production` |

Секреты не должны попадать в шаблоны, статику и git.

## Настройка формы

1. Клиент и сервер проверяют имя, email, телефон, тему, текст и согласие.
2. Скрытое поле `website` отсекает часть ботов.
3. Заявка пишется в SQLite и видна в админке.
4. Если заданы `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`, уходит уведомление. Без них форма всё равно работает.

## Настройка аналитики

События: `hero_cta_click`, `project_open`, `contact_form_start`, `contact_form_submit`, `telegram_click`, `github_click`, `faq_open`, `faq_demo_play`, `faq_demo_pause`, `faq_demo_stop`, `faq_demo_mute`, `faq_demo_cta`, `faq_demo_complete`.

Пока `ANALYTICS_ID` пуст, события копятся в `window.dataLayer`. Подключение счётчика — в `static/js/analytics.js`.

## Деплой

Готовый образ: `Dockerfile`, `Procfile`, `fly.toml`, `render.yaml`.

Исходный код: https://github.com/dimitry8st-prog/st8dom-site

Один клик на Render: https://render.com/deploy?repo=https://github.com/dimitry8st-prog/st8dom-site

Fly.io:

```bash
fly launch --copy-config --yes
fly secrets set SECRET_KEY=... ADMIN_PASSWORD=... SITE_URL=https://<app>.fly.dev FLASK_ENV=production
fly deploy
```

Render: подключите репозиторий, blueprint подхватит `render.yaml`. Задайте `SITE_URL` после выдачи домена.

На хосте:

1. `pip install -r requirements.txt`
2. Задать `SECRET_KEY`, пароль админа, `SITE_URL`, `FLASK_ENV=production`
3. Каталоги `instance/` и `logs/` должны быть доступны для записи
4. `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
5. HTTPS (иначе `SESSION_COOKIE_SECURE` не пустит в админку)
6. Проверить `/robots.txt`, `/sitemap.xml`, форму и `/admin/login/`

SQLite на бесплатном хосте без диска сбрасывается при перезапуске контейнера. Для заявок лучше постоянный диск или внешняя БД.

## Как обновить кейс

Редактируйте словарь в `cases.py`: проблема, решение, роль, статус, репозиторий, ограничения. Не называйте демо промышленным внедрением. Картинки — SVG в `static/images/`. Видео кейса — MP4 в `static/video/` (поле `video`).

## Демо-ролик FAQ-ассистента

Страница кейса: `/cases/faq-assistant/`

Плеер, постер, субтитры и расшифровка уже на сайте. **MP4 и музыка в репозиторий не кладутся как заглушки.** Без них страница показывает HTML-демонстрацию с тем же сценарием (40 секунд), кнопками «Воспроизвести» / «Стоп», переключателем звука и субтитрами.

### Ожидаемые файлы

| Файл | Назначение |
| --- | --- |
| `static/video/faq-assistant-demo.mp4` | Горизонталь 1920×1080, H.264, 35–45 с |
| `static/video/faq-assistant-demo-vertical.mp4` | Вертикаль 1080×1920 |
| `static/video/faq-assistant-poster.webp` | Постер (уже есть) |
| `static/audio/bach-prelude-c-major-bwv846.mp3` | Бах, BWV 846, CC0 (Kimiko Ishizaka) |
| `static/audio/faq-assistant-vo.mp3` | Мужская озвучка диктора (уже есть) |
| `static/subtitles/faq-assistant-ru.vtt` | Субтитры по фразам диктора (уже есть) |

Как выбрать лицензионную запись Баха — в `static/audio/README.md`. Требования к MP4 — в `static/video/README.md`.

### Текст озвучки

Спокойный мужской голос, 135–145 слов в минуту, короткие паузы между блоками:

«Сотрудники ежедневно отвечают на одни и те же вопросы. FAQ-ассистент берёт эту работу на себя. Он использует проверенную базу знаний компании, отвечает клиентам в едином корпоративном стиле, уточняет детали и передаёт сложные обращения специалисту. В результате клиенты получают ответы быстрее, а сотрудники занимаются задачами, где действительно нужен человек. FAQ-ассистент — цифровой сотрудник первой линии».

Музыка в готовом MP4: 8–12% относительно голоса, на важных репликах 6–8%, появление 1 с, затухание 2 с. Не подкладывайте защищённую современную запись.

Кнопка «Обсудить внедрение» ведёт в форму с темой `faq` или в Telegram @dimitry8st.

## Чек-лист перед публикацией

- [ ] CTA ведёт в форму или @dimitry8st, не в канал
- [ ] У каждого кейса свой репозиторий или честная пометка
- [ ] Юридические страницы просмотрены владельцем
- [ ] Сменены `SECRET_KEY` и пароль админа
- [ ] Telegram-уведомления настроены или сознательно выключены
- [ ] Нет секретов в репозитории
- [ ] Форма, 404 и админка проверены на телефоне

## Структура

```
app.py              # приложение и маршруты
config.py           # настройки
cases.py            # содержимое кейсов
models.py / forms.py
wsgi.py / Procfile / Dockerfile   # продакшен
templates/          # Jinja2
static/             # css, js, images, video, audio, subtitles
instance/site.db    # создаётся при запуске
logs/app.log
```
