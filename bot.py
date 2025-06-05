# -------------------------------------
# Файл: bot.py  (добавляем новые команды админа для управления username)
# -------------------------------------
import logging
import os

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

# Загружаем .env
load_dotenv()

# --------------------- Логирование ---------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --------------------- Переменные окружения ---------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("Отсутствует TELEGRAM_BOT_TOKEN в окружении")
    raise RuntimeError("TELEGRAM_BOT_TOKEN обязателен")

# Импорт модулей
from handlers_basic import start, help_command, list_projects
from handlers_testops import button_handler, text_message_handler
from handlers_admin import allow_user, disallow_user, list_allowed


def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Обычные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list_projects", list_projects))

    # Админ-команды (работают с @username)
    application.add_handler(CommandHandler("allow_user", allow_user))
    application.add_handler(CommandHandler("disallow_user", disallow_user))
    application.add_handler(CommandHandler("list_allowed", list_allowed))

    # CallbackQuery (Inline-кнопки)
    application.add_handler(CallbackQueryHandler(button_handler))

    # Текстовые сообщения (кроме команд)
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), text_message_handler)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
