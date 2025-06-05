# Allure TestOps Telegram Bot

Асинхронный Telegram-бот для запуска Job'ов и мониторинга прогонов в Allure TestOps.

## Основные возможности

* 🔁 Запуск Job'ов Allure TestOps через Telegram
* 🔄 Мониторинг статуса прогона (каждые 30 секунд)
* 🔹 Автоматическое уведомление с итоговой статистикой после завершения
* 🕜 Поддержка долгих прогонов (по умолчанию до 12 часов)
* 🔹 Хранение проектов и прав пользователей в MongoDB
* 🔹 Админ-панель для управления правами пользователей
* ✅ Защита от сбоев API (повтор запросов при ошибках 5xx)
* 🔄 Интуитивный интерфейс в Telegram (Reply/Inline клавиатуры)

## Стек технологий

* Python 3.11+
* python-telegram-bot v22.1 (async)
* aiohttp
* pymongo
* python-dotenv
* Allure TestOps API

## Структура проекта

```
bot.py                   # Точка входа
db.py                    # Работа с MongoDB
testops_client.py        # Интеграция с Allure TestOps API
handlers_basic.py        # Базовые команды (start, help)
handlers_testops.py      # Запуск Job'ов и работа с проектами
handlers_admin.py        # Админ-команды
jobs.py                  # Периодические задачи (check_launch_result)
keyboards.py             # Построение клавиатур
utils.py                 # Вспомогательные функции
.env.example             # Пример файла переменных окружения
```

## Установка

1️⃣ Установить зависимости:

```bash
pip install -r requirements.txt
```

2️⃣ Настроить `.env` (пример ниже):

```env
# Настройки Allure TestOps API
TESTOPS_URL=https://your.testops.url
TESTOPS_API_BASE=https://your.testops.url/api
USER_TOKEN=your_testops_api_token

# Настройки Telegram-бота
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Telegram username владельца бота (без символа @)
OWNER_USERNAME=your_admin_telegram_username

# Настройки MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=telegram_bot
MONGO_COLLECTION=projects

# Уровень логирования (DEBUG / INFO / WARNING / ERROR)
LOG_LEVEL=INFO


```

3️⃣ Запустить бота:

```bash
python bot.py
```

## Требования к окружению

* Python 3.11+
* MongoDB (локально или в облаке):

  * Локально: [MongoDB Community Edition](https://www.mongodb.com/try/download/community)
  * В облаке: [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)

## Управление правами пользователей

Только пользователи из белого списка могут запускать Job'ы.

Админ-команды (`OWNER_USERNAME`):

* `/allow_user username` — разрешить пользователю
* `/disallow_user username` — удалить из белого списка
* `/list_allowed` — показать текущий белый список

## Примечания

* Бот поддерживает прогоны любой длительности (по умолчанию тайм-аут 12 ч, настраивается)
* Проверка статуса каждые 30 секунд
* Отправляет результат по завершению
* Использует полностью асинхронный API, эффективен по ресурсам

---

# Allure TestOps Telegram Bot (English)

Asynchronous Telegram bot for launching Jobs and monitoring runs in Allure TestOps.

## Features

* 🔁 Launch Allure TestOps Jobs via Telegram
* 🔄 Monitor run status (every 30 seconds)
* 🔹 Automatic notification with final statistics after completion
* 🕜 Support for long-running runs (default up to 12 hours)
* 🔹 Store projects and user permissions in MongoDB
* 🔹 Admin panel for managing user permissions
* ✅ API error handling with retry on 5xx
* 🔄 User-friendly Telegram interface (Reply/Inline keyboards)

## Tech Stack

* Python 3.11+
* python-telegram-bot v22.1 (async)
* aiohttp
* pymongo
* python-dotenv
* Allure TestOps API

## Project Structure

```
bot.py                   # Entry point
db.py                    # MongoDB integration
testops_client.py        # Allure TestOps API integration
handlers_basic.py        # Basic commands (start, help)
handlers_testops.py      # Launching Jobs and managing projects
handlers_admin.py        # Admin commands
jobs.py                  # Periodic tasks (check_launch_result)
keyboards.py             # Keyboard building
utils.py                 # Utility functions
.env.example             # Environment variables example
```

## Installation

1️⃣ Install dependencies:

```bash
pip install -r requirements.txt
```

2️⃣ Configure `.env`:

```env
# Allure TestOps API settings
TESTOPS_URL=https://your.testops.url
TESTOPS_API_BASE=https://your.testops.url/api
USER_TOKEN=your_testops_api_token

# Telegram bot settings
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Telegram username of the bot owner (without @)
OWNER_USERNAME=your_admin_telegram_username

# MongoDB settings
MONGO_URI=mongodb://localhost:27017
MONGO_DB=telegram_bot
MONGO_COLLECTION=projects

# Logging level (DEBUG / INFO / WARNING / ERROR)
LOG_LEVEL=INFO

```

3️⃣ Run the bot:

```bash
python bot.py
```

## Environment Requirements

* Python 3.11+
* MongoDB (local or cloud):

  * Local: [MongoDB Community Edition](https://www.mongodb.com/try/download/community)
  * Cloud: [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)

## User Permissions Management

Only users from the whitelist can run Jobs.

Admin commands (`OWNER_USERNAME`):

* `/allow_user username` — allow a user
* `/disallow_user username` — remove from whitelist
* `/list_allowed` — show current whitelist

## Notes

* Bot supports runs of any duration (default timeout 12h, configurable)
* Status check every 30 seconds
* Sends result upon completion
* Uses fully asynchronous API & is resource-efficient

## License

MIT License.
