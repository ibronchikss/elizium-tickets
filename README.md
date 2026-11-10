# Тикет-бот (аналог Tickets v2) — Python + discord.py

Полнофункциональный бот тикетов: панели, мульти-панели, формы, треды, транскрипты (HTML),
теги, база знаний, статистика, оценки, SLA, автозакрытие, часы поддержки и **Premium**.
Язык сообщений — русский или английский (`/language`).

## Быстрый запуск

1. **Создайте бота:** https://discord.com/developers/applications → New Application → Bot → Reset Token (скопируйте токен).
2. На странице Bot включите **Privileged Gateway Intents**: `SERVER MEMBERS INTENT` и `MESSAGE CONTENT INTENT`.
3. Установите Python 3.10+ и зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Скопируйте `.env.example` в `.env` и впишите `DISCORD_TOKEN` (и свой ID в `OWNER_IDS`).
5. Запуск:
   ```bash
   python main.py
   ```
6. Пригласите бота командой `/invite` (или через OAuth2 URL Generator: scopes `bot` + `applications.commands`).
7. На сервере выполните **`/setup auto`** — бот сам создаст категорию, лог-канал и первую панель.

> Для мгновенного появления команд на тестовом сервере укажите `DEV_GUILD_ID` в `.env`.
> Глобальные команды появляются в Discord в течение ~1 часа.

## Premium

В `.env` есть переключатель `PREMIUM_FOR_ALL`:

| Значение | Что происходит |
|---|---|
| `true` (по умолчанию) | Все премиум-функции открыты на всех серверах — удобно для личного бота |
| `false` | Premium по ключам: владелец создаёт ключ `/premium genkey`, сервер активирует `/premium activate` |

Команды владельца (ID в `OWNER_IDS`): `/premium genkey`, `/premium grant`, `/premium revoke`.
Лимиты бесплатного тарифа настраиваются в `.env` (`FREE_PANEL_LIMIT`, `FREE_KB_LIMIT`, `FREE_FORM_QUESTIONS`, `FREE_TRANSCRIPT_DAYS`).

**Что даёт Premium:** неограниченные панели и мульти-панели (выпадающее меню / кнопки в одном сообщении),
формы до 25 вопросов (многошаговые), приоритеты тикетов, дежурство `/on-call`, SLA-оповещения,
автозакрытие с предупреждением, оценка поддержки + комментарии, статистика и рейтинг сотрудников,
база знаний без лимита с авто-подсказками и `/faq`, несколько окон часов поддержки,
автоматизация ролей (выдача/снятие роли при открытии/закрытии), свой цвет и подпись, бессрочное хранение транскриптов.

## Команды

**Пользователи:** `/open` `/close` `/transcript` `/gdpr` `/help` `/about` `/invite` `/vote` `/support`

**Поддержка:** `/claim` `/release` `/transfer` `/add` `/remove` `/closerequest` `/priority` `/edit` `/move`
`/tickets list` `/on-call` `/tag use` `/kb search` `/faq`; кнопки в тикете: Закрыть, Взять, Комментарий.

**Администраторы:**
- `/setup auto|limit|toggle|category|thread-parent|log-channel|transcripts-channel|naming|welcome|autoclose|sla|branding|hours-add|hours-clear|hours-show|timezone|show`
- `/panel create|edit|config|role|send|preview|delete|list|show`
- `/multipanel create|edit|add-panel|remove-panel|send|delete|list`
- `/form create|add-question|remove-question|show|list|delete`
- `/tag create|delete|list`, `/kb add|remove|list`
- `/addadmin` `/addsupport` `/removeadmin` `/removesupport` `/staff` `/blacklist` `/language`
- `/stats server|staff|leaderboard|ratings` (Premium)

## Основные возможности

- **Панели:** своё оформление (заголовок, описание, цвет, картинка, эмодзи и стиль кнопки), у каждой панели своя категория,
  роли поддержки, пинг-роли, лимит тикетов, форма, шаблон названия, приветствие, обязательная роль, часы работы.
- **Тикеты-каналы или приватные треды**, закрепление приветствия, авто-добавление дежурных сотрудников.
- **Формы** перед открытием тикета (модальные окна, несколько шагов), ответы попадают в тикет.
- **Закрытие:** с подтверждением, с причиной, по запросу сотрудника (`/closerequest` с таймером), автозакрытие неактивных,
  закрытие при выходе автора. Транскрипт (HTML) уходит в лог-канал и автору в ЛС.
- **Поддержка:** взять/снять/передать, перенос между панелями, приоритеты, теги, база знаний, часы работы и часовой пояс.
- **Контроль:** SLA, чёрный список (пользователи и роли), права `admin` / `support`, логи, оценки с комментариями.
- **Данные:** SQLite (`data/tickets.db`), `/gdpr` удаляет данные пользователя.

## Структура

```
main.py              точка входа
bot/core.py          класс бота, настройки сервера, права, Premium
bot/services.py      логика тикетов (создание, закрытие, claim, SLA и т.д.)
bot/views.py         кнопки, меню, модальные окна, формы
bot/transcript.py    HTML-транскрипты
bot/db.py            SQLite (схема и обёртка)
bot/i18n.py          переводы ru / en
bot/cogs/            слеш-команды (tickets, panels, settings, tags, stats, premium, tasks, general)
```

## Права бота на сервере

Просмотр каналов, отправка сообщений и вложений, встраивания, история сообщений, управление каналами,
ролями, сообщениями и тредами, создание приватных тредов, реакции, внешние эмодзи.
Роль бота должна стоять **выше** ролей, которые он выдаёт (если используете автоматизацию ролей).
