import logging
import os
import re

from telegram import Update
from telegram.ext import ContextTypes

from db import add_allowed_user, remove_allowed_user, list_allowed_users

logger = logging.getLogger(__name__)

# Загружаем список владельцев из переменной окружения
raw = os.getenv("OWNER_USERNAMES", "")
OWNER_USERNAMES = {u.strip() for u in raw.split(",") if u.strip()}


async def allow_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /allow_user <telegram_username>
    Добавляет указанного пользователя (по @username) в белый список.
    Доступна только пользователям из OWNER_USERNAMES.
    """
    from_user = update.effective_user.username
    if from_user not in OWNER_USERNAMES:
        return

    if not context.args:
        return await update.message.reply_text("Использование: /allow_user <telegram_username>")

    raw_username = context.args[0].lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]+", raw_username):
        return await update.message.reply_text(
            "Неверный формат username, используйте только буквы, цифры и подчёркивания."
        )

    try:
        add_allowed_user(raw_username)
    except Exception as e:
        logger.error(f"Не удалось добавить в allowed_users: {e}")
        return await update.message.reply_text("❗ Ошибка при добавлении пользователя.")

    await update.message.reply_text(f"✅ Пользователь @{raw_username} добавлен в белый список.")


async def disallow_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /disallow_user <telegram_username>
    Удаляет указанного пользователя (по @username) из белого списка.
    Доступна только пользователям из OWNER_USERNAMES.
    """
    from_user = update.effective_user.username
    if from_user not in OWNER_USERNAMES:
        return

    if not context.args:
        return await update.message.reply_text("Использование: /disallow_user <telegram_username>")

    raw_username = context.args[0].lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]+", raw_username):
        return await update.message.reply_text(
            "Неверный формат username, используйте только буквы, цифры и подчёркивания."
        )

    try:
        remove_allowed_user(raw_username)
    except Exception as e:
        logger.error(f"Не удалось удалить из allowed_users: {e}")
        return await update.message.reply_text("❗ Ошибка при удалении пользователя.")

    await update.message.reply_text(f"❌ Пользователь @{raw_username} удалён из белого списка.")


async def list_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /list_allowed
    Показывает всех пользователей (@username) из белого списка.
    Доступна только пользователям из OWNER_USERNAMES.
    """
    from_user = update.effective_user.username
    if from_user not in OWNER_USERNAMES:
        return

    ids = list_allowed_users()
    if not ids:
        return await update.message.reply_text("Список разрешённых пользователей пуст.")

    text = "👥 Разрешённые пользователи:\n" + "\n".join(f"• @{u}" for u in ids)
    await update.message.reply_text(text)