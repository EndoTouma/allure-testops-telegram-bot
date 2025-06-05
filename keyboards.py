from typing import Any, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

# --------------------- Константы Reply-клавиатур ---------------------
MAIN_REPLY_KB = ReplyKeyboardMarkup(
    [
        ["▶️ Запустить тест"],
        ["➕ Добавить проект"],
        ["📂 Список проектов"],
        ["ℹ️ Помощь"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

REPLY_MENU = ReplyKeyboardMarkup(
    [["Меню"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)


# --------------------- Построение Inline-клавиатур ---------------------
def build_projects_inline(projects: List[Dict]) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []
    for doc in projects:
        pid = doc["project_id"]
        name = doc["project_name"]
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{name} (ID {pid})", callback_data=f"project_{pid}"
                )
            ]
        )
    keyboard.append(
        [InlineKeyboardButton("➕ Добавить проект", callback_data="add_project")]
    )
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def build_jobs_inline(jobs: List[Dict], project_id: int) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []
    for job in jobs:
        jid = job.get("id")
        jname = job.get("name", f"Job {jid}")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{jname} (ID {jid})", callback_data=f"job_{jid}_{project_id}"
                )
            ]
        )
    keyboard.append(
        [InlineKeyboardButton("⬅️ К проектам", callback_data="run_test")]
    )
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def build_params_inline(
        params: List[Dict],
        collected: Dict[str, Any],
        project_id: int,
        job_id: int,
) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    next_param = None
    for p in params:
        key = p.get("name")
        if key not in collected:
            next_param = p
            break
    
    lines = [f"• {k} = {v}" for k, v in collected.items()]
    chosen_text = "\n".join(lines) if lines else "• (пока ничего не указано)"
    
    if not next_param:
        header = (
            f"📋 Параметры заполнены:\n{chosen_text}\n\n"
            f"Отправьте имя запуска (до 100 символов):"
        )
        return header, None
    
    key = next_param.get("name", "")
    default = next_param.get("defaultValue", "")
    
    header = (
        f"📋 Заполнено:\n{chosen_text}\n\n"
        f"Введите значение для «{key}» или используйте одну из кнопок:\n"
        f"• «✅ По умолчанию ({default})»\n"
        f"• «✏️ Ввести своё значение»\n"
    )
    buttons = [
        [
            InlineKeyboardButton(
                f"✅ По умолчанию ({default})",
                callback_data=f"param_{key}_{default}_{job_id}_{project_id}",
            )
        ],
        [
            InlineKeyboardButton(
                f"✏️ Ввести своё значение",
                callback_data=f"param_{key}_INPUT_{job_id}_{project_id}",
            )
        ],
        [InlineKeyboardButton("⬅️ Назад", callback_data="run_test")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    return header, InlineKeyboardMarkup(buttons)
