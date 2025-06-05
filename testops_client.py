# testops_client.py

import os
import time
import logging
import aiohttp
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

logger = logging.getLogger(__name__)

# --------------------- Переменные окружения ---------------------
# Ожидается, что в окружении заданы TESTOPS_URL (базовый URL, например: https://my.testops.io),
# и USER_TOKEN (API-токен Allure TestOps).
TESTOPS_API_BASE = os.getenv("TESTOPS_API_BASE")
TESTOPS_URL = os.getenv("TESTOPS_URL")
USER_TOKEN = os.getenv("USER_TOKEN", "")

if not TESTOPS_API_BASE or not USER_TOKEN:
    logger.error("В testops_client: отсутствует TESTOPS_URL или USER_TOKEN в окружении.")
    raise RuntimeError("TESTOPS_URL и USER_TOKEN обязательны для работы модуля testops_client")

# Кэширование JWT
_jwt_cache: Dict[str, Any] = {"token": None, "expires_at": 0}


class TestOpsError(Exception):
    """Базовый класс для ошибок TestOps API."""
    pass


async def get_jwt() -> str:
    """
    Асинхронно получает и кеширует JWT из Allure TestOps по API-токену.
    Возвращает актуальный токен (Bearer).
    """
    now = time.time()
    if _jwt_cache["token"] and _jwt_cache["expires_at"] - 30 > now:
        return _jwt_cache["token"]

    url = f"{TESTOPS_API_BASE}/uaa/oauth/token"
    data = {"grant_type": "apitoken", "scope": "openid", "token": USER_TOKEN}
    headers = {"Accept": "application/json"}

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(url, data=data, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error(f"get_jwt: POST {url} failed {resp.status} | {text}")
                    raise TestOpsError(f"Ошибка получения токена: {resp.status}")
                j = await resp.json()
        except aiohttp.ClientError as e:
            logger.error(f"get_jwt: сетевой сбой при запросе токена: {e}")
            raise TestOpsError("Сетевой сбой при получении токена")

    token = j.get("access_token")
    expires_in = j.get("expires_in", 300)
    if not token:
        logger.error("get_jwt: нет поля access_token в ответе")
        raise TestOpsError("В ответе отсутствует access_token")

    _jwt_cache["token"] = token
    _jwt_cache["expires_at"] = now + int(expires_in)
    return token


async def api_request(method: str, path: str, payload: Optional[Dict] = None) -> Any:
    """
    Универсальный асинхронный запрос к TestOps API.
    method: "GET" или "POST".
    path: то, что идёт после базового URL, например: "/project/123".
    payload: для POST – словарь с JSON-телом.
    Возвращает распарсенный JSON.
    """
    jwt = await get_jwt()
    url = f"{TESTOPS_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in (1, 2):  # максимум 2 попытки
            try:
                if method.upper() == "GET":
                    async with session.get(url, headers=headers) as resp:
                        text = await resp.text()
                        if resp.status >= 500 and attempt == 1:
                            logger.warning(f"GET {url} → {resp.status}, retrying...")
                            await asyncio.sleep(2)
                            continue
                        if resp.status >= 400:
                            logger.error(f"GET {url} failed {resp.status} | {text}")
                            raise TestOpsError(f"GET {path} → {resp.status}")
                        return await resp.json()
                
                elif method.upper() == "POST":
                    async with session.post(url, json=payload or {}, headers=headers) as resp:
                        text = await resp.text()
                        if resp.status >= 500 and attempt == 1:
                            logger.warning(f"POST {url} → {resp.status}, retrying...")
                            await asyncio.sleep(2)
                            continue
                        if resp.status >= 400:
                            logger.error(f"POST {url} failed {resp.status} | {text}")
                            raise TestOpsError(f"POST {path} → {resp.status}")
                        return await resp.json()
                
                else:
                    raise TestOpsError(f"Unsupported HTTP method: {method}")
            
            except aiohttp.ClientError as e:
                logger.error(f"api_request: сетевой сбой при запросе {method} {url}: {e}")
                raise TestOpsError("Сетевой сбой при запросе к TestOps")


async def get_project_name(project_id: int) -> str:
    """
    Получает из TestOps имя проекта по его ID.
    """
    data = await api_request("GET", f"/project/{project_id}")
    return data.get("name", f"Проект {project_id}")


async def get_jobs_list(project_id: int) -> List[Dict]:
    """
    Возвращает список Job’ов для данного проекта.
    Если ответ – не список, пытается найти поля "content", "jobs", "elements" или "data".
    """
    data = await api_request("GET", f"/job?projectId={project_id}")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "jobs", "elements", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


async def get_job_details(job_id: int) -> Dict:
    """
    Возвращает детали Job-а, включая параметры, url: GET /api/job/{jobId}.
    """
    data = await api_request("GET", f"/job/{job_id}")
    if not isinstance(data, dict):
        raise TestOpsError(f"Unexpected response for job details: {job_id}")
    return data


async def run_job(job_id: int, launch_name: str, params_list: List[Dict]) -> int:
    """
    Запускает Job с заданным списком параметров.
    Возвращает ID созданного запуска (launch_id).
    """
    payload = {
        "launchName": launch_name,
        "parameters": params_list,
        "selection": {
            "groupsInclude": [],
            "groupsExclude": [],
            "leafsInclude": [],
            "leafsExclude": [],
            "path": [],
            "inverted": False,
        },
        "tags": [],
    }
    data = await api_request("POST", f"/job/{job_id}/run", payload)
    run_id = data.get("id")
    if not run_id:
        logger.error(f"run_job: нет поля id в ответе при запуске job {job_id}")
        raise TestOpsError("Не удалось получить идентификатор запуска")
    return int(run_id)


async def get_launch_info(launch_id: int) -> Dict:
    """
    Возвращает информацию о запуске по ID: статус, флаги и т.д.
    """
    data = await api_request("GET", f"/launch/{launch_id}")
    if not isinstance(data, dict):
        raise TestOpsError(f"Unexpected response for launch info: {launch_id}")
    return data


async def get_launch_statistic(launch_id: int) -> List[Dict]:
    """
    Возвращает статистику по запуску (количество тестов в разных статусах).
    """
    data = await api_request("GET", f"/launch/{launch_id}/statistic")
    if not isinstance(data, list):
        raise TestOpsError(f"Unexpected stats response for launch {launch_id}")
    return data