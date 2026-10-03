"""Тексты бота. Разметка HTML."""

DEFAULT_WELCOME = (
    "👋 <b>Здравствуйте!</b>\n\n"
    "Напишите ваш вопрос, можно с фото, видео и файлами. "
    "Мы ответим прямо здесь."
)

CAPTCHA = "🤖 <b>Проверка</b>\n\nРешите пример: <b>{question}</b>"
CAPTCHA_WRONG = "❌ Неверно. Попытка {attempt} из {total}"
CAPTCHA_LOCKED = "⛔ Слишком много ошибок. Через {seconds} сек. нажмите /start"
CAPTCHA_EXPIRED = "Проверка устарела, нажмите /start"
CAPTCHA_REQUIRED = "Сначала пройдите проверку: /start"
CAPTCHA_OK = "✅ Проверка пройдена"

FLOOD_WARN = "⏳ Слишком часто. Подождите {seconds} сек., до этого сообщения не доставляются."
BANNED = "🚫 Вы заблокированы."
NOT_CONFIGURED = "⚙️ Бот ещё настраивается, напишите чуть позже."
UNSUPPORTED = "Такой тип сообщения не поддерживается."

CARD_NEW = "🆕 <b>Новый пользователь</b>"
CARD_REPEAT = "🔁 <b>Снова нажал /start</b>"
CARD_BODY = "👤 {name}\n🔗 {username}\n🆔 <code>{id}</code>"
FLOOD_GROUP = "⏳ {name} <code>{id}</code> флудит, пауза {seconds} сек."

REPLY_FAILED_BLOCKED = "❌ Не доставлено: <code>{id}</code> остановил бота"
REPLY_FAILED = "❌ Не доставлено <code>{id}</code>: {error}"

BAN_USAGE = (
    "<code>/ban ID причина</code> или реплаем на сообщение\n"
    "<code>/unban ID</code>"
)
BAN_DONE = "🚫 <code>{id}</code> забанен"
BAN_ALREADY = "<code>{id}</code> уже забанен"
UNBAN_DONE = "✅ <code>{id}</code> разбанен"
UNBAN_ALREADY = "<code>{id}</code> не был забанен"
ID_HINT = "Ответьте <code>/id</code> на сообщение пользователя"
