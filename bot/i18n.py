"""Переводы сообщений бота (ru / en).

tr(lang, key, **kw) — берёт строку на нужном языке, при отсутствии — русскую,
при отсутствии и её — сам ключ. Форматирование (str.format) применяется только
если переданы параметры, поэтому строки без параметров могут содержать {user} и т.п.
как шаблоны для utils.fill.
"""
from __future__ import annotations

from typing import Any

RU: dict[str, str] = {
    # --- общее
    "yes": "Да", "no": "Нет", "on": "включено", "off": "выключено", "optional": "необязательно",
    "done": "✅ Готово.",
    "closing": "🔒 Закрываю тикет…",
    "cancelled": "Отменено.",
    "close_cancelled": "Закрытие отменено.",

    # --- ошибки
    "err_generic": "❌ Что-то пошло не так. Попробуйте ещё раз позже.",
    "err_forbidden": "❌ У бота не хватает прав. Проверьте права бота (управление каналами, ролями, сообщениями, тредами).",
    "err_guild_only": "❌ Эта команда работает только на сервере.",
    "err_cooldown": "⏳ Подождите {seconds} сек. перед повторным использованием.",
    "err_not_admin": "❌ Нужны права администратора бота (или «Управление сервером»).",
    "err_not_support": "❌ Эта команда доступна только поддержке.",
    "err_owner_only": "❌ Только для владельца бота.",
    "err_premium": "⭐ Функция «{feature}» доступна в Premium. Подробнее: `/premium status`.",
    "err_not_ticket": "❌ Это не тикет (или он уже закрыт).",
    "err_only_opener": "❌ Это может сделать только автор тикета.",
    "err_cannot_close": "❌ У вас нет прав закрыть этот тикет.",
    "err_blacklisted": "🚫 Вам запрещено открывать тикеты на этом сервере.",
    "err_limit": "❌ У вас уже открыто максимум тикетов ({limit}).",
    "err_hours": "🕒 Сейчас поддержка не работает. Часы работы:\n{hours}",
    "err_required_role": "❌ Для открытия этого тикета нужна роль {role}.",
    "err_panel_disabled": "❌ Эта панель отключена.",
    "err_panel_missing": "❌ Панель не найдена.",
    "err_panel_missing_named": "❌ Панель «{name}» не найдена.",
    "err_panel_exists": "❌ Панель с таким названием уже есть.",
    "err_no_panels": "❌ На сервере ещё нет панелей. Создайте: `/panel create` или `/setup auto`.",
    "err_no_thread_parent": "❌ Не задан канал для тредов. Укажите его: `/setup thread-parent`.",
    "err_role_in_thread": "❌ В треды нельзя добавлять роли — только пользователей.",
    "err_remove_opener": "❌ Нельзя убрать автора тикета.",
    "err_target_not_staff": "❌ Этот пользователь не входит в поддержку.",
    "err_ticket_not_found": "❌ Тикет не найден.",
    "err_no_transcript": "❌ Транскрипт для этого тикета не найден.",
    "err_already_claimed": "❌ Тикет уже взят другим сотрудником.",
    "err_not_claimed": "❌ Тикет никем не взят.",
    "err_not_claimer": "❌ Снять тикет может только тот, кто его взял (или админ).",
    "err_nothing_to_edit": "❌ Укажите, что именно нужно изменить.",
    "err_bad_color": "❌ Неверный цвет. Пример: `#5865F2`.",
    "err_bad_emoji": "❌ Неверный эмодзи.",
    "err_bad_url": "❌ Неверная ссылка (нужна http/https).",
    "err_bad_name": "❌ Неверное название (1–45 символов).",
    "err_bad_length": "❌ Превышена допустимая длина текста.",
    "err_bad_duration": "❌ Неверная длительность. Примеры: `30m`, `2h`, `1d`.",
    "err_bad_hours": "❌ Неверное время. Формат: `ЧЧ:ММ`, дни: `пн-пт` или `1-5`.",
    "err_bad_timezone": "❌ Неизвестный часовой пояс. Пример: `Europe/Moscow`.",
    "err_bad_key": "❌ Неверный или уже использованный ключ.",
    "err_blacklist_staff": "❌ Нельзя заблокировать сотрудника поддержки.",
    "err_warn_gt_hours": "❌ Предупреждение должно быть меньше срока автозакрытия.",
    "err_need_channel": "❌ Укажите канал, в который опубликовать.",
    "err_form_exists": "❌ Форма с таким названием уже есть.",
    "err_form_full": "❌ В форме не может быть больше 25 вопросов.",
    "err_form_missing": "❌ Форма не найдена.",
    "err_no_forms": "❌ Форм пока нет. Создайте: `/form create`.",
    "err_question_missing": "❌ Вопрос с таким номером не найден.",
    "err_multi_count": "❌ В мульти-панели должно быть от 1 до 25 панелей.",
    "err_multi_missing": "❌ Мульти-панель не найдена.",
    "err_no_multis": "❌ Мульти-панелей пока нет.",
    "err_tag_missing": "❌ Тег не найден.",
    "err_kb_missing": "❌ Статья не найдена.",

    # --- кнопки
    "btn_close": "Закрыть", "btn_claim": "Взять", "btn_comment": "Комментарий",
    "btn_confirm": "Подтвердить", "btn_cancel": "Отмена", "btn_continue": "Продолжить",
    "btn_cr_approve": "Закрыть тикет", "btn_cr_deny": "Оставить открытым",
    "btn_open_default": "Открыть тикет",

    # --- панели
    "panel_default_desc": "Нажмите на кнопку ниже, чтобы открыть тикет.",
    "panel_created": "✅ Панель «{name}» создана.",
    "panel_deleted": "🗑️ Панель «{name}» удалена.",
    "panel_published": "📌 Панель опубликована: {url}",
    "panel_send_hint": "Опубликуйте её командой `/panel send name:{name}`.",
    "panels_title": "Панели тикетов",
    "multi_created": "✅ Мульти-панель «{name}» создана.",
    "multis_title": "Мульти-панели",
    "auto_panel_title": "Поддержка",
    "auto_panel_desc": "Нужна помощь? Нажмите кнопку ниже — для вас откроется личный тикет.",
    "setup_auto_done": "✅ Готово! Категория: {category}, лог-канал: {log}. Первая панель создана.",

    # --- формы
    "form_created": "✅ Форма «{name}» создана.",
    "form_empty": "В форме пока нет вопросов.",
    "forms_title": "Формы",
    "form_next": "Шаг {step} из {total}",
    "form_answers": "Ответы на форму",
    "question_added": "✅ Вопрос №{n} добавлен (шагов в форме: {steps}).",

    # --- тикет
    "ticket_created": "✅ Тикет создан: {channel}",
    "ticket_title": "Тикет #{number}",
    "welcome_default": "Здравствуйте, {user}! Опишите вашу проблему — поддержка скоро ответит.",
    "channel_topic": "Тикет #{number} · {user} · {panel}",
    "claimed_msg": "🙋 {user} взял(а) этот тикет.",
    "claimed_ok": "✅ Вы взяли этот тикет.",
    "released_msg": "👋 {user} снял(а) с себя этот тикет.",
    "released_ok": "✅ Вы сняли с себя тикет.",
    "transferred_msg": "🔁 {by} передал(а) тикет сотруднику {user}.",
    "moved_msg": "📂 {user} перенёс(ла) тикет в панель «{panel}».",
    "added_ok": "➕ {target} добавлен(а) в тикет.",
    "removed_ok": "➖ {target} убран(а) из тикета.",
    "pinned_ok": "📌 Сообщение закреплено.",
    "pick_panel": "Выберите тип тикета:",
    "priority_set": "{emoji} {user} установил(а) приоритет: **{level}**.",
    "prio_low": "Низкий", "prio_normal": "Обычный", "prio_high": "Высокий", "prio_urgent": "Срочный",
    "oncall_on": "🟢 Вы на дежурстве: вас будут добавлять в новые тикеты.",
    "oncall_off": "⚪ Дежурство выключено.",
    "tickets_list_title": "Открытые тикеты ({count})",
    "tickets_none": "Открытых тикетов нет.",
    "transcript_sent": "📄 Транскрипт тикета #{number}:",

    # --- закрытие
    "close_confirm": "Вы уверены, что хотите закрыть тикет?",
    "close_denied": "❌ {user} отклонил(а) запрос на закрытие тикета.",
    "close_request_title": "Запрос на закрытие",
    "close_request_msg": "{user} считает, что вопрос решён, и просит закрыть тикет.",
    "close_request_reason": "**Причина:** {reason}",
    "close_request_delay": "Если не ответить, тикет закроется {when}.",
    "close_request_sent": "✅ Запрос отправлен автору тикета.",
    "reason_close_request": "Закрыт по запросу сотрудника (автор не возразил)",
    "reason_autoclose": "Автозакрытие: нет активности {hours} ч.",
    "reason_left": "Автор покинул сервер",
    "autoclose_warning": "⏰ В этом тикете давно нет активности. Он будет закрыт {when}, если вы не ответите.",
    "dm_closed_title": "Ваш тикет #{number} на сервере «{guild}» закрыт",
    "dm_closed_desc": "**Причина:** {reason}",
    "log_closed_title": "Тикет #{number} закрыт",
    "transcript_title": "Транскрипт тикета #{number} — {guild}",

    # --- поля логов
    "f_ticket": "Тикет", "f_opener": "Автор", "f_created_by": "Создал(а)", "f_closed_by": "Закрыл(а)",
    "f_claimed_by": "Ответственный", "f_opened": "Открыт", "f_duration": "Длительность",
    "f_messages": "Сообщений", "f_reason": "Причина", "f_panel": "Панель", "f_subject": "Тема",
    "f_priority": "Приоритет", "f_category": "Категория", "f_channel": "Канал", "f_enabled": "Включена",
    "f_form": "Форма", "f_hours": "Часы поддержки", "f_language": "Язык", "f_limit": "Лимит",
    "f_log_channel": "Лог-канал", "f_naming": "Шаблон имени", "f_ping_roles": "Пинг при открытии",
    "f_support_roles": "Роли поддержки", "f_threads": "Треды", "f_timezone": "Часовой пояс",
    "f_transcripts_channel": "Канал транскриптов",

    # --- оценка
    "survey_title": "Оцените поддержку",
    "survey_desc": "Как вам помогли в тикете? Выберите оценку.",
    "survey_thanks": "Спасибо за оценку! ⭐",
    "survey_already": "Вы уже оценили этот тикет.",
    "survey_comment_title": "Комментарий к оценке",
    "survey_comment_label": "Что можно улучшить?",
    "survey_comment_thanks": "Спасибо за отзыв! 💬",
    "log_comment_title": "Комментарий к тикету #{number}",
    "log_rating_title": "Оценка тикета #{number}",
    "ratings_title": "Последние оценки",

    # --- настройки
    "settings_title": "Настройки тикетов",
    "toggle_set": "✅ Опция «{option}»: {state}.",
    "language_set": "✅ Язык изменён на русский.",
    "staff_title": "Команда поддержки",
    "staff_none": "Список пуст.",
    "staff_added": "✅ {target} добавлен(а) с уровнем **{level}**.",
    "staff_removed": "✅ {target} удалён(а) из уровня **{level}**.",
    "staff_not_found": "❌ {target} не найден(а) в уровне **{level}**.",
    "blacklist_on": "🚫 {target} добавлен(а) в чёрный список тикетов.",
    "blacklist_off": "✅ {target} удалён(а) из чёрного списка.",
    "hours_title": "Часы поддержки",
    "hours_added": "✅ Окно часов добавлено.",
    "hours_none": "Часы не заданы — поддержка принимает тикеты круглосуточно.",

    # --- теги и база знаний
    "tag_saved": "✅ Тег «{name}» сохранён.",
    "tags_title": "Теги", "tags_none": "Тегов пока нет.",
    "kb_title": "База знаний", "kb_none": "Статей пока нет.",
    "kb_added": "✅ Статья #{id} добавлена.",
    "kb_results_title": "Найдено в базе знаний",
    "kb_no_results": "Ничего не найдено.",
    "kb_suggest_title": "💡 Возможно, это поможет",

    # --- статистика
    "stats_title": "Статистика ({period})",
    "stats_staff_title": "Статистика: {user}",
    "stats_none": "Данных пока нет.",
    "stats_opened": "Открыто", "stats_closed": "Закрыто", "stats_open_now": "Открыто сейчас",
    "stats_claimed": "Взято", "stats_messages": "Сообщений",
    "stats_avg_duration": "Среднее время тикета", "stats_first_response": "Первый ответ (среднее)",
    "stats_rating": "Средняя оценка", "stats_by_panel": "По панелям", "stats_by_priority": "По приоритетам",
    "stats_trend": "Динамика", "leaderboard_title": "Рейтинг сотрудников",

    # --- SLA
    "sla_title": "⚠️ Нарушение SLA",
    "sla_desc": "Тикет #{number} ({channel}) от {user} без ответа поддержки уже более {minutes} мин. (создан {since}).",

    # --- premium
    "premium_all": "⭐ На этом боте **Premium открыт для всех серверов**.",
    "premium_none": "Premium не активен.",
    "premium_forever": "⭐ Premium активен **навсегда**.",
    "premium_until": "⭐ Premium активен до {when} ({rel}).",
    "premium_activated": "✅ Premium активирован!",
    "premium_features": "Что входит в Premium",
    "premium_features_list": (
        "• Неограниченное число панелей и мульти-панели\n"
        "• Формы до 25 вопросов (многошаговые)\n"
        "• Приоритеты тикетов, дежурство, SLA-оповещения\n"
        "• Автозакрытие неактивных тикетов с предупреждением\n"
        "• Оценка поддержки после закрытия + комментарии\n"
        "• Статистика, рейтинг сотрудников, отзывы\n"
        "• База знаний без лимита и авто-подсказки, `/faq`\n"
        "• Часы поддержки, автоматизация ролей\n"
        "• Свой цвет и подпись, хранение транскриптов без срока"),
    "feat_hours": "часы поддержки",
    "feat_kb": "база знаний (больше {n} статей)",
    "feat_multistep": "формы (больше {n} вопросов)",
    "feat_panels": "панели (больше {n})",
    "feat_role_automation": "автоматизация ролей",

    # --- общее / справка
    "help_title": "Справка по тикет-боту",
    "help_intro": "Бот тикетов: панели, формы, транскрипты, теги, статистика и Premium.",
    "help_users_h": "👤 Пользователи",
    "help_users": "`/open` — открыть тикет\n`/close` — закрыть тикет\n`/transcript` — получить транскрипт\n`/gdpr` — удалить свои данные",
    "help_staff_h": "🛡️ Поддержка",
    "help_staff": (
        "`/claim` `/release` `/transfer` — управление тикетом\n`/add` `/remove` — участники\n"
        "`/closerequest` — запрос на закрытие\n`/priority` `/edit` `/move`\n`/tag use` `/kb search` `/faq`\n"
        "`/tickets list` `/on-call`"),
    "help_admin_h": "⚙️ Администраторы",
    "help_admin": (
        "`/setup auto` — быстрая настройка\n`/setup …` — параметры сервера\n`/panel …` — панели\n"
        "`/form …` — формы\n`/tag …` `/kb …`\n`/addadmin` `/addsupport` `/staff` `/blacklist`\n`/language`"),
    "help_premium_h": "⭐ Premium",
    "help_premium": "`/premium status` `/premium activate`\n`/multipanel …` `/stats …`\n`/setup autoclose` `/setup sla` `/setup branding`",
    "about_title": "О боте",
    "about_desc": "Тикет-бот в стиле Tickets v2: панели, формы, транскрипты, статистика, Premium.",
    "about_servers": "Серверов", "about_open": "Открытых тикетов", "about_uptime": "Аптайм", "about_latency": "Пинг",
    "invite_text": "🔗 Пригласить бота: {url}",
    "vote_text": "🗳️ Проголосовать: {url}", "vote_none": "Ссылка для голосования не задана.",
    "support_text": "💬 Сервер поддержки: {url}", "support_none": "Сервер поддержки не задан.",
    "gdpr_confirm": "⚠️ Это удалит ваши транскрипты, комментарии и данные дежурства. Повторите команду с `confirm: True`.",
    "gdpr_done": "✅ Ваши данные удалены.",
}

EN: dict[str, str] = {
    "yes": "Yes", "no": "No", "on": "enabled", "off": "disabled", "optional": "optional",
    "done": "✅ Done.",
    "closing": "🔒 Closing the ticket…",
    "cancelled": "Cancelled.",
    "close_cancelled": "Closing cancelled.",

    "err_generic": "❌ Something went wrong. Please try again later.",
    "err_forbidden": "❌ The bot is missing permissions. Check its channel/role/message/thread permissions.",
    "err_guild_only": "❌ This command only works in a server.",
    "err_cooldown": "⏳ Please wait {seconds}s before using this again.",
    "err_not_admin": "❌ You need bot admin rights (or Manage Server).",
    "err_not_support": "❌ This command is for support staff only.",
    "err_owner_only": "❌ Bot owner only.",
    "err_premium": "⭐ “{feature}” requires Premium. See `/premium status`.",
    "err_not_ticket": "❌ This is not a ticket (or it is already closed).",
    "err_only_opener": "❌ Only the ticket opener can do this.",
    "err_cannot_close": "❌ You are not allowed to close this ticket.",
    "err_blacklisted": "🚫 You are not allowed to open tickets on this server.",
    "err_limit": "❌ You already have the maximum number of open tickets ({limit}).",
    "err_hours": "🕒 Support is currently offline. Working hours:\n{hours}",
    "err_required_role": "❌ You need the {role} role to open this ticket.",
    "err_panel_disabled": "❌ This panel is disabled.",
    "err_panel_missing": "❌ Panel not found.",
    "err_panel_missing_named": "❌ Panel “{name}” not found.",
    "err_panel_exists": "❌ A panel with this name already exists.",
    "err_no_panels": "❌ No panels yet. Create one with `/panel create` or `/setup auto`.",
    "err_no_thread_parent": "❌ No thread channel set. Use `/setup thread-parent`.",
    "err_role_in_thread": "❌ Roles can't be added to threads — users only.",
    "err_remove_opener": "❌ You can't remove the ticket opener.",
    "err_target_not_staff": "❌ This user is not support staff.",
    "err_ticket_not_found": "❌ Ticket not found.",
    "err_no_transcript": "❌ No transcript found for this ticket.",
    "err_already_claimed": "❌ This ticket is already claimed by another staff member.",
    "err_not_claimed": "❌ This ticket isn't claimed.",
    "err_not_claimer": "❌ Only the claimer (or an admin) can release the ticket.",
    "err_nothing_to_edit": "❌ Specify what to change.",
    "err_bad_color": "❌ Invalid colour. Example: `#5865F2`.",
    "err_bad_emoji": "❌ Invalid emoji.",
    "err_bad_url": "❌ Invalid URL (http/https required).",
    "err_bad_name": "❌ Invalid name (1–45 characters).",
    "err_bad_length": "❌ Text is too long.",
    "err_bad_duration": "❌ Invalid duration. Examples: `30m`, `2h`, `1d`.",
    "err_bad_hours": "❌ Invalid time. Format: `HH:MM`, days: `mon-fri` or `1-5`.",
    "err_bad_timezone": "❌ Unknown timezone. Example: `Europe/London`.",
    "err_bad_key": "❌ Invalid or already used key.",
    "err_blacklist_staff": "❌ You can't blacklist a staff member.",
    "err_warn_gt_hours": "❌ The warning must be shorter than the auto-close period.",
    "err_need_channel": "❌ Specify a channel to publish to.",
    "err_form_exists": "❌ A form with this name already exists.",
    "err_form_full": "❌ A form can't have more than 25 questions.",
    "err_form_missing": "❌ Form not found.",
    "err_no_forms": "❌ No forms yet. Create one with `/form create`.",
    "err_question_missing": "❌ No question with that number.",
    "err_multi_count": "❌ A multi-panel needs 1–25 panels.",
    "err_multi_missing": "❌ Multi-panel not found.",
    "err_no_multis": "❌ No multi-panels yet.",
    "err_tag_missing": "❌ Tag not found.",
    "err_kb_missing": "❌ Article not found.",

    "btn_close": "Close", "btn_claim": "Claim", "btn_comment": "Comment",
    "btn_confirm": "Confirm", "btn_cancel": "Cancel", "btn_continue": "Continue",
    "btn_cr_approve": "Close ticket", "btn_cr_deny": "Keep open",
    "btn_open_default": "Open a ticket",

    "panel_default_desc": "Click the button below to open a ticket.",
    "panel_created": "✅ Panel “{name}” created.",
    "panel_deleted": "🗑️ Panel “{name}” deleted.",
    "panel_published": "📌 Panel published: {url}",
    "panel_send_hint": "Publish it with `/panel send name:{name}`.",
    "panels_title": "Ticket panels",
    "multi_created": "✅ Multi-panel “{name}” created.",
    "multis_title": "Multi-panels",
    "auto_panel_title": "Support",
    "auto_panel_desc": "Need help? Click the button below and a private ticket will be opened for you.",
    "setup_auto_done": "✅ Done! Category: {category}, log channel: {log}. First panel created.",

    "form_created": "✅ Form “{name}” created.",
    "form_empty": "This form has no questions yet.",
    "forms_title": "Forms",
    "form_next": "Step {step} of {total}",
    "form_answers": "Form answers",
    "question_added": "✅ Question #{n} added (form steps: {steps}).",

    "ticket_created": "✅ Ticket created: {channel}",
    "ticket_title": "Ticket #{number}",
    "welcome_default": "Hello, {user}! Please describe your issue — support will reply shortly.",
    "channel_topic": "Ticket #{number} · {user} · {panel}",
    "claimed_msg": "🙋 {user} claimed this ticket.",
    "claimed_ok": "✅ You claimed this ticket.",
    "released_msg": "👋 {user} released this ticket.",
    "released_ok": "✅ You released the ticket.",
    "transferred_msg": "🔁 {by} transferred the ticket to {user}.",
    "moved_msg": "📂 {user} moved the ticket to panel “{panel}”.",
    "added_ok": "➕ {target} added to the ticket.",
    "removed_ok": "➖ {target} removed from the ticket.",
    "pinned_ok": "📌 Message pinned.",
    "pick_panel": "Choose a ticket type:",
    "priority_set": "{emoji} {user} set the priority to **{level}**.",
    "prio_low": "Low", "prio_normal": "Normal", "prio_high": "High", "prio_urgent": "Urgent",
    "oncall_on": "🟢 You're on call: you'll be added to new tickets.",
    "oncall_off": "⚪ On-call disabled.",
    "tickets_list_title": "Open tickets ({count})",
    "tickets_none": "No open tickets.",
    "transcript_sent": "📄 Transcript of ticket #{number}:",

    "close_confirm": "Are you sure you want to close this ticket?",
    "close_denied": "❌ {user} declined the close request.",
    "close_request_title": "Close request",
    "close_request_msg": "{user} thinks the issue is resolved and asks to close the ticket.",
    "close_request_reason": "**Reason:** {reason}",
    "close_request_delay": "If there is no reply, the ticket will close {when}.",
    "close_request_sent": "✅ Request sent to the ticket opener.",
    "reason_close_request": "Closed on staff request (opener did not object)",
    "reason_autoclose": "Auto-closed: no activity for {hours}h.",
    "reason_left": "Opener left the server",
    "autoclose_warning": "⏰ This ticket has been inactive for a while. It will be closed {when} unless you reply.",
    "dm_closed_title": "Your ticket #{number} in “{guild}” was closed",
    "dm_closed_desc": "**Reason:** {reason}",
    "log_closed_title": "Ticket #{number} closed",
    "transcript_title": "Transcript of ticket #{number} — {guild}",

    "f_ticket": "Ticket", "f_opener": "Opener", "f_created_by": "Created by", "f_closed_by": "Closed by",
    "f_claimed_by": "Claimed by", "f_opened": "Opened", "f_duration": "Duration",
    "f_messages": "Messages", "f_reason": "Reason", "f_panel": "Panel", "f_subject": "Subject",
    "f_priority": "Priority", "f_category": "Category", "f_channel": "Channel", "f_enabled": "Enabled",
    "f_form": "Form", "f_hours": "Support hours", "f_language": "Language", "f_limit": "Limit",
    "f_log_channel": "Log channel", "f_naming": "Name template", "f_ping_roles": "Ping on open",
    "f_support_roles": "Support roles", "f_threads": "Threads", "f_timezone": "Timezone",
    "f_transcripts_channel": "Transcripts channel",

    "survey_title": "Rate our support",
    "survey_desc": "How did we do? Pick a rating.",
    "survey_thanks": "Thanks for rating! ⭐",
    "survey_already": "You've already rated this ticket.",
    "survey_comment_title": "Rating comment",
    "survey_comment_label": "What could be improved?",
    "survey_comment_thanks": "Thanks for the feedback! 💬",
    "log_comment_title": "Comment on ticket #{number}",
    "log_rating_title": "Rating of ticket #{number}",
    "ratings_title": "Latest ratings",

    "settings_title": "Ticket settings",
    "toggle_set": "✅ Option “{option}”: {state}.",
    "language_set": "✅ Language changed to English.",
    "staff_title": "Support team",
    "staff_none": "The list is empty.",
    "staff_added": "✅ {target} added with level **{level}**.",
    "staff_removed": "✅ {target} removed from level **{level}**.",
    "staff_not_found": "❌ {target} not found in level **{level}**.",
    "blacklist_on": "🚫 {target} added to the ticket blacklist.",
    "blacklist_off": "✅ {target} removed from the blacklist.",
    "hours_title": "Support hours",
    "hours_added": "✅ Hours window added.",
    "hours_none": "No hours set — support accepts tickets 24/7.",

    "tag_saved": "✅ Tag “{name}” saved.",
    "tags_title": "Tags", "tags_none": "No tags yet.",
    "kb_title": "Knowledge base", "kb_none": "No articles yet.",
    "kb_added": "✅ Article #{id} added.",
    "kb_results_title": "Found in the knowledge base",
    "kb_no_results": "Nothing found.",
    "kb_suggest_title": "💡 This might help",

    "stats_title": "Statistics ({period})",
    "stats_staff_title": "Statistics: {user}",
    "stats_none": "No data yet.",
    "stats_opened": "Opened", "stats_closed": "Closed", "stats_open_now": "Open now",
    "stats_claimed": "Claimed", "stats_messages": "Messages",
    "stats_avg_duration": "Average ticket time", "stats_first_response": "First response (avg)",
    "stats_rating": "Average rating", "stats_by_panel": "By panel", "stats_by_priority": "By priority",
    "stats_trend": "Trend", "leaderboard_title": "Staff leaderboard",

    "sla_title": "⚠️ SLA breach",
    "sla_desc": "Ticket #{number} ({channel}) from {user} has had no staff response for over {minutes} min (created {since}).",

    "premium_all": "⭐ **Premium is unlocked for all servers** on this bot.",
    "premium_none": "Premium is not active.",
    "premium_forever": "⭐ Premium is active **forever**.",
    "premium_until": "⭐ Premium active until {when} ({rel}).",
    "premium_activated": "✅ Premium activated!",
    "premium_features": "What Premium includes",
    "premium_features_list": (
        "• Unlimited panels and multi-panels\n"
        "• Forms up to 25 questions (multi-step)\n"
        "• Ticket priorities, on-call, SLA alerts\n"
        "• Auto-close of inactive tickets with a warning\n"
        "• Support rating after closing + comments\n"
        "• Statistics, staff leaderboard, feedback\n"
        "• Unlimited knowledge base with auto-suggestions, `/faq`\n"
        "• Support hours, role automation\n"
        "• Custom colour and footer, unlimited transcript storage"),
    "feat_hours": "support hours",
    "feat_kb": "knowledge base (more than {n} articles)",
    "feat_multistep": "forms (more than {n} questions)",
    "feat_panels": "panels (more than {n})",
    "feat_role_automation": "role automation",

    "help_title": "Ticket bot help",
    "help_intro": "Ticket bot: panels, forms, transcripts, tags, statistics and Premium.",
    "help_users_h": "👤 Users",
    "help_users": "`/open` — open a ticket\n`/close` — close the ticket\n`/transcript` — get a transcript\n`/gdpr` — delete your data",
    "help_staff_h": "🛡️ Support",
    "help_staff": (
        "`/claim` `/release` `/transfer` — manage the ticket\n`/add` `/remove` — participants\n"
        "`/closerequest` — ask to close\n`/priority` `/edit` `/move`\n`/tag use` `/kb search` `/faq`\n"
        "`/tickets list` `/on-call`"),
    "help_admin_h": "⚙️ Admins",
    "help_admin": (
        "`/setup auto` — quick setup\n`/setup …` — server options\n`/panel …` — panels\n"
        "`/form …` — forms\n`/tag …` `/kb …`\n`/addadmin` `/addsupport` `/staff` `/blacklist`\n`/language`"),
    "help_premium_h": "⭐ Premium",
    "help_premium": "`/premium status` `/premium activate`\n`/multipanel …` `/stats …`\n`/setup autoclose` `/setup sla` `/setup branding`",
    "about_title": "About",
    "about_desc": "A Tickets v2–style ticket bot: panels, forms, transcripts, statistics, Premium.",
    "about_servers": "Servers", "about_open": "Open tickets", "about_uptime": "Uptime", "about_latency": "Latency",
    "invite_text": "🔗 Invite the bot: {url}",
    "vote_text": "🗳️ Vote: {url}", "vote_none": "No vote link configured.",
    "support_text": "💬 Support server: {url}", "support_none": "No support server configured.",
    "gdpr_confirm": "⚠️ This deletes your transcripts, comments and on-call data. Re-run the command with `confirm: True`.",
    "gdpr_done": "✅ Your data has been deleted.",
}

LANGS: dict[str, dict[str, str]] = {"ru": RU, "en": EN}


def tr(lang: str, key: str, **kw: Any) -> str:
    text = LANGS.get(lang, RU).get(key)
    if text is None:
        text = RU.get(key, key)
    if not kw:
        return text
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError):
        return text
