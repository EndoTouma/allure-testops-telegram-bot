import logging

from telegram import ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import testops_client as toc
import time
from keyboards import REPLY_MENU

logger = logging.getLogger(__name__)


async def check_launch_result(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Периодически (каждые 30 секунд) проверяет, завершился ли прогон (launch) и, если да,
    отправляет итоговую статистику и кнопку «Меню», после чего удаляет задачу из очереди.
    """
    job_data = context.job.data
    attempt = job_data.get("attempt", 1)
    chat_id = job_data["chat_id"]
    loading_message_id = job_data["loading_message_id"]
    launch_id = job_data["launch_id"]
    
    # Установка времени начала (если ещё не было)
    start_ts = job_data.get("start_ts")
    if start_ts is None:
        start_ts = time.time()
        context.job.data["start_ts"] = start_ts
    
    # Лимит времени ожидания (в секундах)
    max_duration_sec = 12 * 3600  # 12 часов
    
    elapsed = time.time() - start_ts
    if elapsed > max_duration_sec:
        logger.warning(
            f"check_launch_result: превышено время ожидания для launch {launch_id} ({elapsed / 3600:.1f} ч), удаляю задачу.")
        context.job.schedule_removal()
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Тайм-аут ожидания завершения прогона. Проверьте вручную в Allure TestOps.",
            reply_markup=REPLY_MENU,
        )
        return
    
    # Получаем launch_info
    try:
        launch_info = await toc.get_launch_info(launch_id)
    except toc.TestOpsError as e:
        logger.error(f"check_launch_result: ошибка API при получении {launch_id}: {e}")
        return
    
    # Если ещё не закрыт — ждём дальше
    if not launch_info.get("closed", False):
        return
    
    # Прогон закрыт — получаем статистику
    try:
        stats = await toc.get_launch_statistic(launch_id)
    except toc.TestOpsError as e:
        logger.error(f"check_launch_result: не удалось получить статистику для {launch_id}: {e}")
        stats = []
    
    passed_count = sum(
        item["count"] for item in stats if item.get("status", "").upper() == "PASSED"
    )
    failed_count = sum(
        item["count"] for item in stats if item.get("status", "").upper() == "FAILED"
    )
    skipped_count = sum(
        item["count"]
        for item in stats
        if item.get("status", "").upper() not in ("PASSED", "FAILED")
    )
    total_count = passed_count + failed_count + skipped_count
    
    stats_text = (
        f"🎯 Всего тестов: <b>{total_count}</b>\n"
        f"🟢 Passed: <b>{passed_count}</b>\n"
        f"🔴 Failed: <b>{failed_count}</b>\n"
        f"⚪ Skipped: <b>{skipped_count}</b>"
    )
    
    run_link = f"{toc.TESTOPS_URL}/launch/{launch_id}"
    final_text = (
        f"✅ Прогон <b>ID {launch_id}</b> завершён.\n"
        f"📊 Статистика выполнения:\n{stats_text}\n\n"
        f"🔗 <a href=\"{run_link}\">Перейти в Allure TestOps</a>"
    )
    
    # Отправляем итоговое сообщение
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=final_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_to_message_id=loading_message_id,
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as e:
        logger.error(f"check_launch_result: не удалось отправить сообщение о завершении: {e}")
    
    # Предлагаем «Меню»
    await context.bot.send_message(
        chat_id=chat_id,
        text="Для продолжения работы нажмите «Меню»:",
        reply_markup=REPLY_MENU,
    )
    
    # Удаляем задачу из очереди
    context.job.schedule_removal()
