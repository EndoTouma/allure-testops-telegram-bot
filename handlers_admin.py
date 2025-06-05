import logging
import os

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from db import add_allowed_user, remove_allowed_user, list_allowed_users

logger = logging.getLogger(__name__)

# Ваш Telegram username (без @), который имеет право выдавать/снимать доступ
OWNER_USERNAME = os.getenv("OWNER_USERNAME")  # <- Замените на ваш username без символа @


async def allow_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /allow_user <telegram_username>
    Добавляет указанного пользователя (по @username) в белый список.
    Доступна только OWNER_USERNAME.
    """
    from_user = update.effective_user.username
    if from_user != OWNER_USERNAME:
        return

    if not context.args:
        return await update.message.reply_text("Использование: /allow_user <telegram_username>")

    raw = context.args[0].lstrip("@")
    if not raw.isalnum():
        return await update.message.reply_text("Неверный формат username, используйте только буквы/цифры.")

    try:
        add_allowed_user(raw)
    except Exception as e:
        logger.error(f"Не удалось добавить в allowed_users: {e}")
        return await update.message.reply_text("❗ Ошибка при добавлении пользователя.")

    await update.message.reply_text(f"✅ Пользователь @{raw} добавлен в белый список.")


async def disallow_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /disallow_user <telegram_username>
    Удаляет указанного пользователя (по @username) из белого списка.
    Доступна только OWNER_USERNAME.
    """
    from_user = update.effective_user.username
    if from_user != OWNER_USERNAME:
        return

    if not context.args:
        return await update.message.reply_text("Использование: /disallow_user <telegram_username>")

    raw = context.args[0].lstrip("@")
    if not raw.isalnum():
        return await update.message.reply_text("Неверный формат username, используйте только буквы/цифры.")

    try:
        remove_allowed_user(raw)
    except Exception as e:
        logger.error(f"Не удалось удалить из allowed_users: {e}")
        return await update.message.reply_text("❗ Ошибка при удалении пользователя.")

    await update.message.reply_text(f"❌ Пользователь @{raw} удалён из белого списка.")


async def list_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /list_allowed
    Показывает всех пользователей (@username) из белого списка.
    Доступна только OWNER_USERNAME.
    """
    from_user = update.effective_user.username
    if from_user != OWNER_USERNAME:
        return

    ids = list_allowed_users()
    if not ids:
        return await update.message.reply_text("Список разрешённых пользователей пуст.")

    text = "👥 Разрешённые пользователи:\n" + "\n".join(f"• @{u}" for u in ids)
    await update.message.reply_text(text)
