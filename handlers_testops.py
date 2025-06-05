import logging
import re
from typing import Any, Dict, List

from pymongo import errors as mongo_errors
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import testops_client as toc
from db import get_user_projects, find_project, add_project, is_user_allowed, delete_project
from handlers_basic import help_command, list_projects
from jobs import check_launch_result
from keyboards import (
    build_jobs_inline,
    build_params_inline,
    MAIN_REPLY_KB,
    REPLY_MENU,
)
from testops_client import TESTOPS_URL
from utils import extract_project_id, notify_error

logger = logging.getLogger(__name__)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает все нажатия кнопок (InlineKeyboard) для:
    - выбора проекта (run_test)
    - просмотра/добавления проектов (add_project, project_<id>)
    - выбора Job и параметров (job_<id>_<project>, param_…)
    - удаления проекта (delete_<id>)
    """
    query = update.callback_query
    await query.answer()
    username = query.from_user.username
    if not username or not is_user_allowed(username):
        await query.answer(text="❌ У вас нет прав для взаимодействия с ботом.", show_alert=True)
        return
    
    data = query.data
    user_id = query.from_user.id
    
    try:
        # 0) Помощь через кнопку
        if data == "help":
            help_text = (
                "ℹ️ Краткая информация:\n"
                "▶️ Запустить тест — выбрать проект и Job для запуска.\n"
                "➕ Добавить проект — сохранить ссылку на проект.\n"
                "📂 Список проектов — посмотреть ваши проекты.\n"
                "ℹ️ Помощь — показать этот текст.\n\n"
                "Используйте кнопки главного меню ниже."
            )
            await query.edit_message_text(help_text, reply_markup=MAIN_REPLY_KB)
            return
        
        # 1) Вернуться в главное меню (Reply-клавиатура)
        if data == "back_to_main":
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None,
                    )
                except Exception:
                    pass
            try:
                await context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id,
                )
            except Exception:
                pass
            return
        
        # 2) Отмена всех операций — возвращаем «Главное меню»
        if data == "cancel":
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None,
                    )
                except Exception:
                    pass
            context.user_data.clear()
            try:
                await context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id,
                )
            except Exception:
                pass
            return
        
        # 2.1) Удаление конкретного проекта
        if data.startswith("delete_"):
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None,
                    )
                except Exception:
                    pass
            
            try:
                project_id = int(data.split("_", 1)[1])
            except (IndexError, ValueError):
                return await notify_error(
                    query, context, "Неверный ID проекта при удалении.", retry_data="list_projects"
                )
            
            # Удаляем проект из БД
            try:
                deleted = delete_project(user_id, project_id)
            except Exception as e:
                logger.error(f"Ошибка при удалении проекта {project_id}: {e}")
                return await query.edit_message_text(
                    "❗ Не удалось удалить проект из базы. Повторите позже.",
                    reply_markup=None
                )
            
            if not deleted:
                return await query.edit_message_text(
                    f"❗ Проект ID {project_id} не найден в вашем списке.",
                    reply_markup=None
                )
            
            # Проект успешно удалён: уведомляем и перечитываем список
            await query.edit_message_text(
                f"✅ Проект с ID {project_id} успешно удалён.\n"
                f"Обновляю список..."
            )
            return await list_projects(update, context)
        
        # 2.2) Подтверждение запуска
        if data == "launch_confirm":
            # Убираем inline-клавиатуру у сообщения с резюме
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None
                    )
                except Exception:
                    pass
            
            # Достаем «черновик» запуска из user_data
            pending = context.user_data.pop("pending_launch", None)
            if not pending:
                return await query.edit_message_text(
                    "❗ Нет данных для запуска. Повторите процедуру.",
                    reply_markup=None
                )
            
            job_id = pending["job_id"]
            launch_name = pending["launch_name"]
            params_list = pending["params_list"]
            display_params = pending.get("display_params", [])
            
            loading = await query.edit_message_text("⌛ Запуск Job…")
            
            # Запускаем Job через TestOps API
            try:
                run_id = await toc.run_job(job_id, launch_name, params_list)
            except toc.TestOpsError as e:
                logger.exception(f"Ошибка запуска Job: {e}")
                return await query.edit_message_text(
                    "❗ Не удалось запустить Job. Попробуйте позже.",
                    reply_markup=MAIN_REPLY_KB
                )
            
            # Формируем информацию о запущенном прогона (с именами параметров)
            if display_params:
                params_lines = "\n".join(f"• {name} = {value}" for name, value in display_params)
            else:
                params_lines = "нет параметров"
            
            run_link = f"{TESTOPS_URL}/launch/{run_id}"
            started_text = (
                f"✅ Запущено!\n"
                f"📌 Имя запуска: <b>{launch_name}</b>\n"
                f"📋 Параметры:\n<code>{params_lines}</code>\n\n"
                f"ID прогона: <b>{run_id}</b>\n"
                f"🔗 <a href=\"{run_link}\">Перейти в Allure TestOps</a>\n\n"
                "Жду завершения и потом выдам результаты..."
            )
            
            # Редактируем сообщение «⌛ Запуск…» в «✅ Запущено…»
            await context.bot.edit_message_text(
                text=started_text,
                chat_id=loading.chat_id,
                message_id=loading.message_id,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
            # Планируем проверку результата
            context.job_queue.run_repeating(
                check_launch_result,
                interval=30,
                first=30,
                data={
                    "chat_id": loading.chat_id,
                    "loading_message_id": loading.message_id,
                    "launch_id": run_id,
                },
                name=f"check_launch_{run_id}"
            )
            
            # Отправляем пользователю кнопку возврата к списку действий
            await update.callback_query.message.reply_text(
                "Для показа списка действий нажмите кнопку ниже:",
                reply_markup=REPLY_MENU
            )
            
            context.user_data.clear()
            return
        
        # 2.3) Отмена запуска
        if data == "launch_cancel":
            # Убираем inline-клавиатуру у сообщения с резюме
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None
                    )
                except Exception:
                    pass
            
            # Удаляем «черновик» запуска, если он был
            context.user_data.pop("pending_launch", None)
            
            await query.edit_message_text(
                "❌ Операция отменена.",
                reply_markup=MAIN_REPLY_KB
            )
            return
        
        # 3) Запустить тест (вывод списка проектов)
        if data == "run_test":
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None
                    )
                except Exception:
                    pass
            
            try:
                docs = get_user_projects(user_id)
            except Exception as e:
                logger.error(f"MongoDB error (run_test): {e}")
                return await notify_error(
                    query, context, "Ошибка БД при получении проектов.", retry_data="run_test"
                )
            
            if not docs:
                text = (
                    "📂 Список проектов пуст.\n"
                    "Нажмите «➕ Добавить проект», чтобы добавить проект."
                )
                buttons = InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("➕ Добавить проект", callback_data="add_project")],
                        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
                        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
                    ]
                )
                return await query.edit_message_text(text, parse_mode="HTML", reply_markup=buttons)
            
            keyboard = []
            for doc in docs:
                pid = doc["project_id"]
                name = doc["project_name"]
                keyboard.append(
                    [InlineKeyboardButton(f"{name} (ID {pid})", callback_data=f"project_{pid}")]
                )
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
            markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📂 Ваши проекты:", reply_markup=markup
            )
            context.user_data["last_msg_id_with_buttons"] = query.message.message_id
            return
        
        # 4) Добавить проект
        if data == "add_project":
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None,
                    )
                except Exception:
                    pass
            
            cancel_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]
            )
            
            await query.edit_message_text(
                "📂 Отправьте номер проекта в Allure TestOps:\n",
                parse_mode="HTML",
                reply_markup=cancel_markup,
            )
            context.user_data.clear()
            context.user_data["adding_project"] = True
            return
        
        # 5) Выбрать проект по ID
        if data.startswith("project_"):
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None,
                    )
                except Exception:
                    pass
            
            try:
                project_id = int(data.split("_", 1)[1])
            except (IndexError, ValueError):
                return await notify_error(
                    query, context, "Неверный ID проекта.", retry_data="run_test"
                )
            
            proj_doc = find_project(user_id, project_id)
            if not proj_doc:
                return await notify_error(
                    query, context, "Проект не найден.", retry_data="run_test"
                )
            project_name = proj_doc["project_name"]
            
            await query.edit_message_text(
                f"⌛ Загрузка Job’ов для проекта «{project_name}»…"
            )
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            try:
                jobs = await toc.get_jobs_list(project_id)
            except toc.TestOpsError as e:
                logger.error(f"Error getting jobs list: {e}")
                return await notify_error(
                    query,
                    context,
                    "Ошибка API при получении Job’ов.",
                    retry_data=f"project_{project_id}",
                )
            
            if not jobs:
                return await query.edit_message_text(
                    f"❗ У проекта «{project_name}» нет Job’ов.", reply_markup=None
                )
            
            context.user_data["current_project_id"] = project_id
            context.user_data["current_project_name"] = project_name
            
            await query.edit_message_text(
                f"📋 Job’ы проекта «{project_name}»:",
                reply_markup=build_jobs_inline(jobs, project_id),
            )
            context.user_data["last_msg_id_with_buttons"] = query.message.message_id
            return
        
        # 6) Выбрать Job
        if data.startswith("job_"):
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None,
                    )
                except Exception:
                    pass
            
            parts = data.split("_")
            if len(parts) != 3:
                return await notify_error(
                    query, context, "Неверный формат callback.", retry_data="run_test"
                )
            _, job_id_str, project_id_str = parts
            try:
                job_id = int(job_id_str)
                project_id = int(project_id_str)
            except ValueError:
                return await notify_error(
                    query, context, "Неверный ID Job.", retry_data="run_test"
                )
            
            context.user_data["current_job_id"] = job_id
            context.user_data["current_project_id"] = project_id
            context.user_data["collected_params"] = {}
            
            await query.edit_message_text("⌛ Загрузка деталей Job…")
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            try:
                job_obj = await toc.get_job_details(job_id)
            except toc.TestOpsError as e:
                logger.error(f"Error getting job details: {e}")
                return await notify_error(
                    query,
                    context,
                    "Ошибка API при получении деталей Job.",
                    retry_data=f"job_{job_id}_{project_id}",
                )
            
            params = job_obj.get("parameters", [])
            context.user_data["current_job_name"] = job_obj.get(
                "name", f"Job {job_id}"
            )
            context.user_data["current_params"] = params
            
            # Если нет параметров – сразу просим имя запуска
            if not params:
                context.user_data["awaiting_launch_name"] = True
                context.user_data["awaiting_launch_job"] = job_id
                context.user_data["awaiting_launch_project"] = project_id
                return await query.edit_message_text(
                    "У этого Job нет параметров.\n\n❗ Отправьте имя запуска (до 100 символов):"
                )
            
            # Иначе – спрашиваем первый параметр
            header, markup = build_params_inline(params, {}, project_id, job_id)
            sent = await query.edit_message_text(header, reply_markup=markup)
            context.user_data["last_msg_id_with_buttons"] = sent.message_id
            return
        
        # 7) Заполнение параметров (по кнопке)
        if data.startswith("param_"):
            last_buttons = context.user_data.pop("last_msg_id_with_buttons", None)
            if last_buttons:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=query.message.chat_id,
                        message_id=last_buttons,
                        reply_markup=None,
                    )
                except Exception:
                    pass
            
            parts = data.split("_", 4)
            if len(parts) != 5:
                return await notify_error(
                    query, context, "Неверный формат параметра.", retry_data="run_test"
                )
            _, key, raw_value, job_id_str, project_id_str = parts
            
            try:
                job_id = int(job_id_str)
                project_id = int(project_id_str)
            except ValueError:
                return await notify_error(
                    query, context, "Неверный ID при параметре.", retry_data="run_test"
                )
            
            # Если нужно вводить своё значение — переключаемся в text_message_handler
            if raw_value == "INPUT":
                context.user_data["awaiting_param_key"] = key
                context.user_data["awaiting_param_job"] = job_id
                context.user_data["awaiting_param_project"] = project_id
                return await query.edit_message_text(
                    f"❗ Введите значение для параметра «{key}»:"
                )
            
            params: List[Dict] = context.user_data.get("current_params", [])
            collected: Dict[str, Any] = context.user_data.setdefault(
                "collected_params", {}
            )
            
            if raw_value == "SKIP":
                pass
            else:
                collected[key] = raw_value
            
            # Проверяем, остались ли ещё параметры
            next_param = None
            for p in params:
                if p.get("name") not in collected:
                    next_param = p
                    break
            
            if not next_param:
                context.user_data["awaiting_launch_name"] = True
                context.user_data["awaiting_launch_job"] = job_id
                context.user_data["awaiting_launch_project"] = project_id
                return await query.edit_message_text(
                    "Все параметры указаны.\n\n❗ Отправьте имя запуска (до 100 символов):"
                )
            
            header, markup = build_params_inline(params, collected, project_id, job_id)
            sent = await query.edit_message_text(header, reply_markup=markup)
            context.user_data["last_msg_id_with_buttons"] = sent.message_id
            return
        
        return await notify_error(query, context, "Неизвестная команда.", retry_data="run_test")
    
    except Exception as exc:
        logger.exception(f"Ошибка в button_handler: {exc}")
        try:
            await notify_error(
                update_or_query=query, context=context, message="Внутренняя ошибка.", retry_data="run_test"
            )
        except:
            pass


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает текстовые сообщения для:
    - «▶️ Запустить тест» и «➕ Добавить проект» (имитирует CallbackQuery)
    - Добавление проекта (флаг adding_project)
    - Ввод собственного значения параметра (awaiting_param_key)
    - Ввод имени запуска (awaiting_launch_name)
    - Текст «Меню» и «Отмена»
    """
    username = update.effective_user.username
    if not username or not is_user_allowed(username):
        # Если пользователь не в белом списке, отправляем ему текстовое сообщение
        await update.message.reply_text("❌ У вас нет прав для взаимодействия с ботом.")
        return
    text = update.message.text.strip()
    user_data = context.user_data
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    
    try:
        normalized = text.lower()
        
        # 0) «▶️ Запустить тест»
        if normalized in ("▶️ запустить тест", "➤ запустить тест", "запустить тест"):
            class FakeQuery:
                def __init__(self, message, user):
                    self.data = "run_test"
                    self.message = message
                    self.from_user = user
                
                async def answer(self, *args, **kwargs):
                    return
                
                async def edit_message_text(self, *args, **kwargs):
                    return await self.message.reply_text(*args, **kwargs)
            
            class FakeUpdate:
                def __init__(self, fake_query, message):
                    self.callback_query = fake_query
                    self.effective_chat = message.chat
                    self.effective_user = message.from_user
            
            fake_query = FakeQuery(update.message, update.effective_user)
            fake_update = FakeUpdate(fake_query, update.message)
            return await button_handler(fake_update, context)
        
        # 0.1) «➕ Добавить проект»
        if normalized in ("➕ добавить проект", "добавить проект"):
            class FakeQuery:
                def __init__(self, message, user):
                    self.data = "add_project"
                    self.message = message
                    self.from_user = user
                
                async def answer(self, *args, **kwargs):
                    return
                
                async def edit_message_text(self, *args, **kwargs):
                    return await self.message.reply_text(*args, **kwargs)
            
            class FakeUpdate:
                def __init__(self, fake_query, message):
                    self.callback_query = fake_query
                    self.effective_chat = message.chat
                    self.effective_user = message.from_user
            
            fake_query = FakeQuery(update.message, update.effective_user)
            fake_update = FakeUpdate(fake_query, update.message)
            return await button_handler(fake_update, context)
        
        # 0.2) «📂 Список проектов»
        if normalized in ("📂 список проектов", "список проектов"):
            return await list_projects(update, context)
        
        # 0.3) «ℹ️ Помощь»
        if normalized in ("ℹ️ помощь", "помощь", "/help"):
            return await help_command(update, context)
        
        # 1) Добавление проекта (ожидание ссылки)
        if user_data.get("adding_project"):
            pid = extract_project_id(text)
            if pid is None:
                return await update.message.reply_text(
                    "❗ Не удалось распознать ID.\nОтправьте ID существующего проекта в AllureTestOps",
                    parse_mode="HTML",
                    reply_markup=ReplyKeyboardRemove(),
                )
            existing = find_project(user_id, pid)
            if existing:
                user_data.pop("adding_project", None)
                return await update.message.reply_text(
                    f"❗ Проект ID {pid} уже добавлен.", reply_markup=MAIN_REPLY_KB
                )
            try:
                project_name = await toc.get_project_name(pid)
            except toc.TestOpsError as e:
                logger.error(f"Не удалось получить проект {pid}: {e}")
                user_data.pop("adding_project", None)
                return await update.message.reply_text(
                    f"❗ Ошибка при получении проекта (ID {pid}).",
                    reply_markup=MAIN_REPLY_KB,
                )
            try:
                add_project(user_id, pid, project_name)
            except mongo_errors.DuplicateKeyError:
                user_data.pop("adding_project", None)
                return await update.message.reply_text(
                    f"❗ Проект ID {pid} уже добавлен.", reply_markup=MAIN_REPLY_KB
                )
            except Exception as e:
                logger.error(f"Ошибка записи в MongoDB: {e}")
                user_data.pop("adding_project", None)
                return await update.message.reply_text(
                    "❗ Не удалось сохранить проект в базу.", reply_markup=MAIN_REPLY_KB
                )
            user_data.pop("adding_project", None)
            return await update.message.reply_text(
                f"✅ Проект «{project_name}» добавлен.", reply_markup=MAIN_REPLY_KB
            )
        
        # 2) Ввод собственного значения параметра
        if user_data.get("awaiting_param_key"):
            key = user_data.pop("awaiting_param_key")
            job_id = user_data.pop("awaiting_param_job", None)
            project_id = user_data.pop("awaiting_param_project", None)
            if job_id is None or project_id is None:
                return await notify_error(
                    update, context, "Ошибка при вводе параметра.", retry_data="run_test"
                )
            collected = user_data.setdefault("collected_params", {})
            collected[key] = text
            
            params: List[Dict] = user_data.get("current_params", [])
            next_param = None
            for p in params:
                if p.get("name") not in collected:
                    next_param = p
                    break
            if not next_param:
                user_data["awaiting_launch_name"] = True
                user_data["awaiting_launch_job"] = job_id
                user_data["awaiting_launch_project"] = project_id
                return await update.message.reply_text(
                    "Все параметры заданы.\n\n❗ Отправьте имя запуска (до 100 символов):",
                    reply_markup=ReplyKeyboardRemove(),
                )
            
            header, markup = build_params_inline(
                params, collected, project_id, job_id
            )
            sent = await update.message.reply_text(header, reply_markup=markup)
            user_data["last_msg_id_with_buttons"] = sent.message_id
            return
        
        # 3) Ввод имени запуска
        if user_data.get("awaiting_launch_name"):
            raw_name = text
            job_id = user_data.pop("awaiting_launch_job", None)
            project_id = user_data.pop("awaiting_launch_project", None)
            user_data.pop("awaiting_launch_name", None)
            
            if job_id is None or project_id is None:
                return await notify_error(
                    update, context, "Ошибка при вводе имени.", retry_data="run_test"
                )
            
            if not re.match(r"^[\w\-\s]{1,100}$", raw_name):
                return await update.message.reply_text(
                    "❗ Недопустимый формат имени: только буквы, цифры, пробел, дефис, подчёркивание, до 100 символов.",
                    reply_markup=MAIN_REPLY_KB,
                )
            
            launch_name = raw_name
            collected = user_data.get("collected_params", {})
            params_meta: List[Dict] = user_data.get("current_params", [])
            
            # Собираем список параметров для TestOps API
            params_list = [
                {"id": p["id"], "value": collected[p["name"]]}
                for p in params_meta
                if p["name"] in collected
            ]
            # Собираем «человеческое» отображение (имя ↔ значение)
            display_params = [
                (p["name"], collected[p["name"]])
                for p in params_meta
                if p["name"] in collected
            ]
            
            # Сохраняем «черновик» запуска в user_data, включая display_params
            user_data["pending_launch"] = {
                "job_id": job_id,
                "project_id": project_id,
                "launch_name": launch_name,
                "params_list": params_list,
                "display_params": display_params,
            }
            
            # Формируем текст проверки перед запуском
            if collected:
                params_lines = "\n".join(f"• {k} = {v}" for k, v in collected.items())
            else:
                params_lines = "нет параметров"
            
            confirmation_text = (
                f"🔍 <b>Проверьте перед запуском:</b>\n\n"
                f"📌 <b>Имя запуска:</b> {launch_name}\n"
                f"📋 <b>Параметры:</b>\n<code>{params_lines}</code>\n\n"
                "Нажмите «▶️ Запустить» для запуска или «❌ Отменить» для отмены."
            )
            
            confirm_keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("▶️ Запустить", callback_data="launch_confirm")],
                    [InlineKeyboardButton("❌ Отменить", callback_data="launch_cancel")],
                ]
            )
            
            sent = await update.message.reply_text(
                confirmation_text,
                parse_mode="HTML",
                reply_markup=confirm_keyboard
            )
            user_data["last_msg_id_with_buttons"] = sent.message_id
            return
        
        # 4) Текст «Отмена»
        if normalized == "отмена":
            user_data.clear()
            return await update.message.reply_text(
                "Операция отменена.", reply_markup=MAIN_REPLY_KB
            )
        
        # 5) Нераспознанное сообщение
        return await update.message.reply_text(
            "⚠️ Я не понял запрос. Воспользуйтесь кнопками главного меню ниже.",
            reply_markup=MAIN_REPLY_KB,
        )
    
    except Exception as exc:
        logger.exception(f"Ошибка в text_message_handler: {exc}")
        return await notify_error(update, context, "Внутренняя ошибка.", retry_data="run_test")
