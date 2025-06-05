import os
import logging
from pymongo import MongoClient, errors as mongo_errors
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = "telegram_bot"
PROJECTS_COLLECTION = "projects"
ALLOWED_COLLECTION = "allowed_users"

mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo_client[MONGO_DB]
projects_col = db[PROJECTS_COLLECTION]
allowed_col = db[ALLOWED_COLLECTION]


try:
    projects_col.create_index([("user_id", 1), ("project_id", 1)], unique=True)
except mongo_errors.PyMongoError as e:
    logger.warning(f"Не удалось создать индекс для projects: {e}")

try:
    allowed_col.create_index([("username", 1)], unique=True)
except mongo_errors.PyMongoError as e:
    logger.warning(f"Не удалось создать индекс для allowed_users: {e}")


def is_user_allowed(username: str) -> bool:
    """
    Возвращает True, если в коллекции allowed_users есть документ с данным username.
    """
    try:
        return allowed_col.find_one({"username": username}) is not None
    except Exception as e:
        logger.error(f"DB.is_user_allowed: {e}")
        return False


def add_allowed_user(username: str) -> None:
    """
    Добавляет username в коллекцию allowed_users.
    Если уже есть—просто игнорируем DuplicateKeyError.
    """
    try:
        allowed_col.insert_one({"username": username})
    except mongo_errors.DuplicateKeyError:
        pass
    except Exception as e:
        logger.error(f"DB.add_allowed_user: {e}")
        raise


def remove_allowed_user(username: str) -> None:
    """
    Удаляет username из коллекции allowed_users.
    """
    try:
        allowed_col.delete_one({"username": username})
    except Exception as e:
        logger.error(f"DB.remove_allowed_user: {e}")
        raise


def list_allowed_users() -> List[str]:
    """
    Возвращает список всех username из allowed_users.
    """
    try:
        return [doc["username"] for doc in allowed_col.find({})]
    except Exception as e:
        logger.error(f"DB.list_allowed_users: {e}")
        return []


def get_user_projects(user_id: int) -> List[Dict]:
    """
    Возвращает список документов проектов для данного user_id.
    """
    try:
        return list(projects_col.find({"user_id": user_id}))
    except Exception as e:
        logger.error(f"DB.get_user_projects: {e}")
        raise


def find_project(user_id: int, project_id: int) -> Optional[Dict]:
    """
    Возвращает документ проекта по user_id + project_id или None, если не найден.
    """
    try:
        return projects_col.find_one({"user_id": user_id, "project_id": project_id})
    except Exception as e:
        logger.error(f"DB.find_project: {e}")
        raise


def add_project(user_id: int, project_id: int, project_name: str) -> None:
    """
    Вставляет новый проект в MongoDB. Если уже существует — бросает mongo_errors.DuplicateKeyError.
    """
    try:
        projects_col.insert_one(
            {
                "user_id": user_id,
                "project_id": project_id,
                "project_name": project_name,
            }
        )
    except mongo_errors.DuplicateKeyError:
        raise
    except Exception as e:
        logger.error(f"DB.add_project: {e}")
        raise
    
def delete_project(user_id: int, project_id: int) -> bool:
    """
    Удаляет проект с заданным project_id для пользователя user_id.
    Возвращает True, если удаление прошло успешно.
    """
    try:
        result = projects_col.delete_one({"user_id": user_id, "project_id": project_id})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"DB.delete_project: {e}")
        raise