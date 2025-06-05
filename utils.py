import re
from typing import Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

# Регулярное выражение для извлечения ID из URL проекта
PROJECT_ID_REGEX = re.compile(r"/?(\d+)")

async def notify_error(
    update_or_query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    message: str = "Произошла ошибка. Повторить?",
    retry_data: Optional[str] = None,
):
    """
    Уведомление об ошибке с кнопками «🔄 Повторить» (если retry_data задан) и «❌ Отмена».
    Если update_or_query — настоящий Update (то есть из text_message_handler), присылает новое сообщение.
    Если это CallbackQuery, редактирует текущее сообщение.
    """
    buttons = []
    if retry_data:
        buttons.append([InlineKeyboardButton("🔄 Повторить", callback_data=retry_data)])
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    markup = InlineKeyboardMarkup(buttons)

    if isinstance(update_or_query, Update) and update_or_query.message:
        await update_or_query.message.reply_text(message, reply_markup=markup)
    else:
        await update_or_query.edit_message_text(message, reply_markup=markup)


async def remove_reply_keyboard(update: Update):
    """
    Быстрое удаление ReplyKeyboard (ReplyKeyboardRemove).
    Используется там, где нужно убрать клавиатуру из чата.
    """
    await update.message.reply_text("", reply_markup=ReplyKeyboardRemove())


def extract_project_id(text: str) -> Optional[int]:
    """
    Парсит текст вида https://.../projects/123 или /projects/123 и возвращает 123 (int).
    Если не нашёл — возвращает None.
    """
    match = PROJECT_ID_REGEX.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None