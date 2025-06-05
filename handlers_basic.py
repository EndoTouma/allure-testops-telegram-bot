import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from keyboards import MAIN_REPLY_KB
from db import get_user_projects, delete_project

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start — отправляет приветственное сообщение с MAIN_REPLY_KB.
    """
    await update.message.reply_text(
        "Привет! Я бот для запуска тестов через Allure TestOps.\n"
        "Используйте кнопку «▶️ Запустить тест» для начала.",
        reply_markup=MAIN_REPLY_KB,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /help — показывает справочный текст с MAIN_REPLY_KB.
    """
    help_text = (
        "ℹ️ Краткая информация:\n"
        "▶️ Запустить тест — выбрать проект и Job для запуска.\n"
        "➕ Добавить проект — добавить проект.\n"
        "📂 Список проектов — посмотреть ваши проекты.\n"
        "ℹ️ Помощь — показать этот текст.\n"
        "\n"
        "Используйте кнопки главного меню ниже."
    )
    await update.message.reply_text(help_text, reply_markup=MAIN_REPLY_KB)


async def list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /list_projects — выводит список проектов из MongoDB
    с inline-кнопками «Удалить» для каждого проекта.
    """
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        docs = get_user_projects(user_id)
    except Exception as e:
        logger.error(f"MongoDB error (list_projects): {e}")
        if query:
            return await query.message.reply_text(
                "❗ Ошибка при запросе к БД.", reply_markup=MAIN_REPLY_KB
            )
        else:
            return await update.message.reply_text(
                "❗ Ошибка при запросе к БД.", reply_markup=MAIN_REPLY_KB
            )
    
    if not docs:
        if query:
            return await query.message.reply_text(
                "📂 Список проектов пуст.", reply_markup=MAIN_REPLY_KB
            )
        else:
            return await update.message.reply_text(
                "📂 Список проектов пуст.", reply_markup=MAIN_REPLY_KB
            )
    
    text = "📂 Ваши проекты (нажмите «❌ Удалить», чтобы убрать из списка):\n"
    for doc in docs:
        text += f"• {doc['project_name']} (ID {doc['project_id']})\n"
    
    keyboard = []
    for doc in docs:
        pid = doc["project_id"]
        name = doc["project_name"]
        keyboard.append([
            InlineKeyboardButton(
                f"❌ Удалить \"{name}\" (ID {pid})",
                callback_data=f"delete_{pid}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])
    markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        sent = await query.message.reply_text(text, reply_markup=markup)
    else:
        sent = await update.message.reply_text(text, reply_markup=markup)
    
    context.user_data["last_msg_id_with_buttons"] = sent.message_id
