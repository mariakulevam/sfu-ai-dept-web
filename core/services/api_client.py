"""
Клиент REST API кафедральной системы (Department Portal API).
Бэкенд: FastAPI команды Риты, документация: /docs (Swagger).

Соответствует ARCHITECTURE.md и README.md v1.0.

Особенности:
  • JWT-токены (access + refresh), Bearer-авторизация
  • ФИО разнесено на name/surname/patronymic
  • 6 ролей: student, headman, teacher, deputy_head, dean, admin
  • Объявления со статусами и автоархивированием
  • Документы с visibility (массив ролей)
  • Расписание по группам или преподавателям
  • Посещаемость через одноразовые QR-токены (15 мин)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from django.conf import settings


TIMEOUT = 15


# ═══════════════════════════════════════════════════════════════
#  Низкоуровневые помощники
# ═══════════════════════════════════════════════════════════════

def _headers(token: Optional[str] = None, json_body: bool = False) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _handle(response: requests.Response) -> Any:
    """Единая обработка ответа: возвращает данные или бросает RuntimeError."""
    try:
        data = response.json() if response.content else None
    except ValueError:
        data = None

    if response.ok:
        return data

    detail = f"Ошибка запроса к серверу (HTTP {response.status_code})"
    if isinstance(data, dict) and "detail" in data:
        if isinstance(data["detail"], list):
            detail = "; ".join(str(item) for item in data["detail"])
        else:
            detail = str(data["detail"])

    raise RuntimeError(detail)


def _url(path: str) -> str:
    return f"{settings.FASTAPI_API_BASE}{path}"


def get_media_url(relative_path: Optional[str]) -> Optional[str]:
    """Преобразовать относительный путь файла (например '/uploads/avatars/...') в полный URL."""
    if not relative_path:
        return None
    if relative_path.startswith("http://") or relative_path.startswith("https://"):
        return relative_path
    # Берём базу без /api/v1
    base = settings.FASTAPI_API_BASE.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[:-len("/api/v1")]
    if not relative_path.startswith("/"):
        relative_path = "/" + relative_path
    return f"{base}{relative_path}"


# ═══════════════════════════════════════════════════════════════
#  АВТОРИЗАЦИЯ — /auth/*
# ═══════════════════════════════════════════════════════════════

def login_user(email: str, password: str) -> Dict[str, Any]:
    """
    POST /auth/login — вход.
    Form-data: username, password (по OAuth2PasswordRequestForm).
    Возвращает: {access_token, refresh_token, token_type}.
    """
    response = requests.post(
        _url("/auth/login"),
        data={"username": email, "password": password},
        timeout=TIMEOUT,
    )
    return _handle(response)


def register_user(name: str, surname: str, email: str, password: str,
                  patronymic: Optional[str] = None) -> Dict[str, Any]:
    """POST /auth/register — регистрация. Роль автоматически student."""
    body = {
        "name": name,
        "surname": surname,
        "email": email,
        "password": password,
    }
    if patronymic:
        body["patronymic"] = patronymic
    response = requests.post(
        _url("/auth/register"),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def logout_user(refresh_token: str) -> None:
    """POST /auth/logout — отзыв refresh-токена."""
    response = requests.post(
        _url("/auth/logout"),
        json={"refresh_token": refresh_token},
        headers=_headers(json_body=True),
        timeout=TIMEOUT,
    )
    _handle(response)


def refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    """POST /auth/refresh — обновление access-токена."""
    response = requests.post(
        _url("/auth/refresh"),
        json={"refresh_token": refresh_token},
        headers=_headers(json_body=True),
        timeout=TIMEOUT,
    )
    return _handle(response)


def get_current_user(token: str) -> Dict[str, Any]:
    """GET /auth/me — данные текущего пользователя."""
    response = requests.get(
        _url("/auth/me"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


# ═══════════════════════════════════════════════════════════════
#  ПОЛЬЗОВАТЕЛИ — /users/*
# ═══════════════════════════════════════════════════════════════

def list_users(token: str, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """GET /users — список пользователей (для headman/admin)."""
    response = requests.get(
        _url("/users"),
        headers=_headers(token),
        params={"skip": skip, "limit": limit},
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def admin_create_user(token: str, name: str, surname: str, email: str,
                      role: str, patronymic: Optional[str] = None,
                      password: Optional[str] = None) -> Dict[str, Any]:
    """POST /users — создание пользователя администратором.

    Для ролей teacher/headman/dean/deputy_head пароль генерируется на сервере
    и отправляется на email. Для student/admin пароль обязателен.
    """
    body: Dict[str, Any] = {
        "name": name,
        "surname": surname,
        "email": email,
        "role": role,
    }
    if patronymic:
        body["patronymic"] = patronymic
    if password:
        body["password"] = password
    response = requests.post(
        _url("/users"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def delete_user(token: str, user_id: int) -> None:
    """DELETE /users/{id} — удаление пользователя (только admin)."""
    response = requests.delete(
        _url(f"/users/{user_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _handle(response)


def get_user(token: str, user_id: int) -> Dict[str, Any]:
    """GET /users/{id} — профиль конкретного пользователя."""
    response = requests.get(
        _url(f"/users/{user_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def update_user(token: str, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PUT /users/{id} — обновление профиля."""
    response = requests.put(
        _url(f"/users/{user_id}"),
        headers=_headers(token, json_body=True),
        json=data,
        timeout=TIMEOUT,
    )
    return _handle(response)


def change_password(token: str, user_id: int,
                    old_password: str, new_password: str) -> None:
    """PATCH /users/{id}/password — смена пароля."""
    response = requests.patch(
        _url(f"/users/{user_id}/password"),
        headers=_headers(token, json_body=True),
        json={"old_password": old_password, "new_password": new_password},
        timeout=TIMEOUT,
    )
    _handle(response)


def set_avatar(token: str, document_id: int) -> Dict[str, Any]:
    """PATCH /users/me/avatar — установить аватар из ранее загруженного документа."""
    response = requests.patch(
        _url("/users/me/avatar"),
        headers=_headers(token),
        params={"document_id": document_id},
        timeout=TIMEOUT,
    )
    return _handle(response)


def upload_avatar(token: str, file_path: str, file_name: str = "avatar.png") -> Dict[str, Any]:
    """Загрузить файл картинки как аватар: создаёт документ + ставит его аватаром.
    
    Возвращает обновлённые данные пользователя.
    """
    # Сначала загружаем как документ с категорией avatar
    data = {
        "title": "avatar",
        "category": "other",
        "visibility": "private",
    }
    with open(file_path, "rb") as fh:
        files = {"file": (file_name, fh)}
        response = requests.post(
            _url("/documents"),
            headers=_headers(token),
            data=data,
            files=files,
            timeout=TIMEOUT * 2,
        )
    doc = _handle(response)
    # Теперь ставим этот документ аватаром
    return set_avatar(token, doc["id"])


def sync_lessons(token: str) -> Dict[str, Any]:
    """POST /lessons/sync — синхронизация расписания с edu.sfu-kras.ru (только admin/dean)."""
    response = requests.post(
        _url("/lessons/sync"),
        headers=_headers(token),
        timeout=60,  # синхронизация может занять время
    )
    return _handle(response)


# ═══════════════════════════════════════════════════════════════
#  ОБЪЯВЛЕНИЯ — /announcements/*
# ═══════════════════════════════════════════════════════════════

def list_announcements(token: str, status: Optional[str] = None,
                       limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
    """GET /announcements — список объявлений с фильтром по статусу."""
    params: Dict[str, Any] = {"skip": skip, "limit": limit}
    if status:
        params["status"] = status
    response = requests.get(
        _url("/announcements"),
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def get_announcement(token: str, announcement_id: int) -> Dict[str, Any]:
    """GET /announcements/{id} — конкретное объявление."""
    response = requests.get(
        _url(f"/announcements/{announcement_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def create_announcement(token: str, title: str, content: str,
                        target_group_ids: Optional[List[int]] = None,
                        target_stream_ids: Optional[List[int]] = None,
                        publish_at: Optional[str] = None,
                        expires_at: Optional[str] = None) -> Dict[str, Any]:
    """POST /announcements — создание объявления."""
    body: Dict[str, Any] = {"title": title, "content": content}
    if target_group_ids:
        body["target_group_ids"] = target_group_ids
    if target_stream_ids:
        body["target_stream_ids"] = target_stream_ids
    if publish_at:
        body["publish_at"] = publish_at
    if expires_at:
        body["expires_at"] = expires_at

    response = requests.post(
        _url("/announcements"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def update_announcement(token: str, announcement_id: int,
                        data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /announcements/{id} — редактирование."""
    response = requests.patch(
        _url(f"/announcements/{announcement_id}"),
        headers=_headers(token, json_body=True),
        json=data,
        timeout=TIMEOUT,
    )
    return _handle(response)


def archive_announcement(token: str, announcement_id: int) -> Dict[str, Any]:
    """PATCH /announcements/{id}/archive — перевести в архив."""
    response = requests.patch(
        _url(f"/announcements/{announcement_id}/archive"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def restore_announcement(token: str, announcement_id: int) -> Dict[str, Any]:
    """PATCH /announcements/{id}/restore — восстановить из архива."""
    response = requests.patch(
        _url(f"/announcements/{announcement_id}/restore"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def delete_announcement(token: str, announcement_id: int) -> None:
    """DELETE /announcements/{id}"""
    response = requests.delete(
        _url(f"/announcements/{announcement_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _handle(response)


# ═══════════════════════════════════════════════════════════════
#  СОБЫТИЯ — /events/*
# ═══════════════════════════════════════════════════════════════

def list_events(token: str, from_dt: Optional[str] = None,
                to_dt: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /events — список событий с фильтром по дате."""
    params: Dict[str, Any] = {}
    if from_dt:
        params["from_dt"] = from_dt
    if to_dt:
        params["to_dt"] = to_dt
    response = requests.get(
        _url("/events"),
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def get_event(token: str, event_id: int) -> Dict[str, Any]:
    """GET /events/{id}"""
    response = requests.get(
        _url(f"/events/{event_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def create_event(token: str, title: str, starts_at: str, ends_at: str,
                 annotation: Optional[str] = None,
                 room_id: Optional[int] = None) -> Dict[str, Any]:
    """POST /events — создание события."""
    body: Dict[str, Any] = {
        "title": title,
        "starts_at": starts_at,
        "ends_at": ends_at,
    }
    if annotation:
        body["annotation"] = annotation
    if room_id:
        body["room_id"] = room_id

    response = requests.post(
        _url("/events"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def update_event(token: str, event_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PUT /events/{id}"""
    response = requests.put(
        _url(f"/events/{event_id}"),
        headers=_headers(token, json_body=True),
        json=data,
        timeout=TIMEOUT,
    )
    return _handle(response)


def delete_event(token: str, event_id: int) -> None:
    """DELETE /events/{id}"""
    response = requests.delete(
        _url(f"/events/{event_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _handle(response)


def upload_event_image(token: str, event_id: int, file_path: str) -> Dict[str, Any]:
    """POST /events/{id}/image — загрузить картинку."""
    with open(file_path, "rb") as fh:
        files = {"file": (file_path.split("/")[-1], fh, "image/jpeg")}
        response = requests.post(
            _url(f"/events/{event_id}/image"),
            headers=_headers(token),  # без Content-Type — пусть выставит requests
            files=files,
            timeout=TIMEOUT * 2,
        )
    return _handle(response)


# ═══════════════════════════════════════════════════════════════
#  ДОКУМЕНТЫ — /documents/*
# ═══════════════════════════════════════════════════════════════

def list_documents(token: str) -> List[Dict[str, Any]]:
    """GET /documents — список с фильтром по visibility (на сервере)."""
    response = requests.get(
        _url("/documents"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def get_document(token: str, doc_id: str) -> Dict[str, Any]:
    """GET /documents/{id} — метаданные документа."""
    response = requests.get(
        _url(f"/documents/{doc_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def upload_document(token: str, title: str, category: str,
                    visibility: List[str], file_path: str,
                    description: Optional[str] = None) -> Dict[str, Any]:
    """POST /documents — загрузка документа."""
    visibility_str = ",".join(visibility)
    data = {
        "title": title,
        "category": category,
        "visibility": visibility_str,
    }
    if description:
        data["description"] = description

    with open(file_path, "rb") as fh:
        files = {"file": (file_path.split("/")[-1], fh)}
        response = requests.post(
            _url("/documents"),
            headers=_headers(token),
            data=data,
            files=files,
            timeout=TIMEOUT * 2,
        )
    return _handle(response)


def document_download_url(doc_id: str) -> str:
    """URL для скачивания документа (передаётся в шаблон)."""
    return _url(f"/documents/{doc_id}/download")


def update_document(token: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """PUT /documents/{id} — изменение метаданных."""
    response = requests.put(
        _url(f"/documents/{doc_id}"),
        headers=_headers(token, json_body=True),
        json=data,
        timeout=TIMEOUT,
    )
    return _handle(response)


def delete_document(token: str, doc_id: str) -> None:
    """DELETE /documents/{id}"""
    response = requests.delete(
        _url(f"/documents/{doc_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _handle(response)


# ═══════════════════════════════════════════════════════════════
#  ГРУППЫ И ПОТОКИ — /groups/*, /streams/*
# ═══════════════════════════════════════════════════════════════

def list_groups(token: str) -> List[Dict[str, Any]]:
    """GET /groups — список групп."""
    response = requests.get(
        _url("/groups"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def get_group(token: str, group_id: int) -> Dict[str, Any]:
    """GET /groups/{id}"""
    response = requests.get(
        _url(f"/groups/{group_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def list_streams(token: str) -> List[Dict[str, Any]]:
    """GET /streams — список потоков."""
    response = requests.get(
        _url("/streams"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


# ═══════════════════════════════════════════════════════════════
#  АУДИТОРИИ — /rooms/*
# ═══════════════════════════════════════════════════════════════

def list_rooms(token: str) -> List[Dict[str, Any]]:
    """GET /rooms — список аудиторий."""
    response = requests.get(
        _url("/rooms"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


# ═══════════════════════════════════════════════════════════════
#  РАСПИСАНИЕ — /lessons/*
# ═══════════════════════════════════════════════════════════════

def lessons_by_group(token: str, group_id: int,
                     week: Optional[int] = None) -> List[Dict[str, Any]]:
    """GET /lessons/group/{group_id}"""
    params = {"week": week} if week is not None else None
    response = requests.get(
        _url(f"/lessons/group/{group_id}"),
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def lessons_by_teacher(token: str, teacher_id: int,
                       week: Optional[int] = None) -> List[Dict[str, Any]]:
    """GET /lessons/teacher/{teacher_id}"""
    params = {"week": week} if week is not None else None
    response = requests.get(
        _url(f"/lessons/teacher/{teacher_id}"),
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    return _handle(response) or []


# ═══════════════════════════════════════════════════════════════
#  ПОСЕЩАЕМОСТЬ — /attendance/*
# ═══════════════════════════════════════════════════════════════

def create_attendance_token(token: str, lesson_id: int) -> Dict[str, Any]:
    """POST /attendance/token/{lesson_id} — создать QR-токен (живёт 15 мин)."""
    response = requests.post(
        _url(f"/attendance/token/{lesson_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def get_qr_image_url(lesson_id: int) -> str:
    """URL картинки QR-кода (передаётся в <img src=...>)."""
    return _url(f"/attendance/token/{lesson_id}/qr")


def scan_qr(token: str, qr_token: str) -> Dict[str, Any]:
    """POST /attendance/scan/{token} — отметиться по QR (для студента)."""
    response = requests.post(
        _url(f"/attendance/scan/{qr_token}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def mark_attendance_manually(token: str, lesson_id: int,
                             student_id: int) -> Dict[str, Any]:
    """POST /attendance/manual/{lesson_id}/{student_id} — ручная отметка."""
    response = requests.post(
        _url(f"/attendance/manual/{lesson_id}/{student_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def lesson_attendance(token: str, lesson_id: int) -> List[Dict[str, Any]]:
    """GET /attendance/lesson/{lesson_id} — журнал занятия."""
    response = requests.get(
        _url(f"/attendance/lesson/{lesson_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def student_attendance(token: str, student_id: int) -> List[Dict[str, Any]]:
    """GET /attendance/student/{student_id} — посещаемость студента."""
    response = requests.get(
        _url(f"/attendance/student/{student_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


# ═══════════════════════════════════════════════════════════════
#  ЧАТЫ — /chats/*
# ═══════════════════════════════════════════════════════════════

def list_chats(token: str) -> List[Dict[str, Any]]:
    """GET /chats — список моих чатов."""
    response = requests.get(
        _url("/chats"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def open_direct_chat(token: str, other_user_id: int) -> Dict[str, Any]:
    """POST /chats/direct/{user_id} — открыть личный чат (создаст если нет)."""
    response = requests.post(
        _url(f"/chats/direct/{other_user_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def chat_messages(token: str, chat_id: int,
                  limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """GET /chats/{id}/messages — история сообщений."""
    response = requests.get(
        _url(f"/chats/{chat_id}/messages"),
        headers=_headers(token),
        params={"limit": limit, "offset": offset},
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def get_chat_ws_url(chat_id: int, access_token: str) -> str:
    """URL для WebSocket-подключения к чату."""
    # ws:// или wss:// — зависит от схемы FastAPI
    base = settings.FASTAPI_ROOT_URL.replace("http://", "ws://").replace("https://", "wss://")
    return f"{base}/api/v1/chats/{chat_id}/ws?token={access_token}"


# ═══════════════════════════════════════════════════════════════
#  СПРАВОЧНИКИ И УТИЛИТЫ ДЛЯ ШАБЛОНОВ
# ═══════════════════════════════════════════════════════════════

ROLE_LABELS = {
    "student":     "студент",
    "headman":     "староста",
    "teacher":     "преподаватель",
    "dean":        "заведующий кафедрой",
    "deputy_head": "заместитель заведующего",
    "admin":       "администратор",
}

TEACHER_POSITION_LABELS = {
    "assistant":           "ассистент",
    "lecturer":            "преподаватель",
    "senior_lecturer":     "старший преподаватель",
    "associate_professor": "доцент",
    "professor":           "профессор",
    "sfu_professor":       "профессор СФУ",
    "acting_head":         "и.о. заведующего кафедрой",
}

ANNOUNCEMENT_STATUS_LABELS = {
    "draft":     "черновик",
    "scheduled": "запланировано",
    "published": "опубликовано",
    "archived":  "архив",
}

ANNOUNCEMENT_STATUS_BADGES = {
    "draft":     "neutral",
    "scheduled": "warning",
    "published": "success",
    "archived":  "neutral",
}

CATEGORY_LABELS = {
    "order":    "приказ",
    "method":   "методическое",
    "vkr":      "темы ВКР",
    "template": "шаблон",
    "other":    "прочее",
}


def full_name(user: Dict[str, Any]) -> str:
    """Собирает ФИО из полей name/surname/patronymic."""
    if not user:
        return ""
    parts = [
        user.get("surname", ""),
        user.get("name", ""),
        user.get("patronymic") or "",
    ]
    return " ".join(p for p in parts if p).strip()


def short_name(user: Dict[str, Any]) -> str:
    """Сокращённое ФИО: «Фамилия И. О.»"""
    if not user:
        return ""
    surname = user.get("surname", "")
    name = user.get("name", "")
    patronymic = user.get("patronymic") or ""
    result = surname
    if name:
        result += f" {name[:1]}."
    if patronymic:
        result += f" {patronymic[:1]}."
    return result.strip()


def make_initials(user_or_name) -> str:
    """Инициалы из dict пользователя или строки."""
    if isinstance(user_or_name, dict):
        name = user_or_name.get("name", "")
        surname = user_or_name.get("surname", "")
        if surname or name:
            return ((surname[:1] if surname else "") + (name[:1] if name else "")).upper() or "·"
    if isinstance(user_or_name, str):
        parts = [p for p in user_or_name.split() if p]
        if len(parts) >= 2:
            return (parts[0][:1] + parts[1][:1]).upper()
        return parts[0][:2].upper() if parts else "·"
    return "·"


def can_create_content(role: Optional[str]) -> bool:
    """Кто имеет право создавать объявления, события."""
    return role in {"teacher", "headman", "admin"}


def can_upload_documents(role: Optional[str]) -> bool:
    """Кто загружает документы."""
    return role in {"teacher", "headman", "admin"}


def can_manage_attendance(role: Optional[str]) -> bool:
    """Кто работает с QR-токенами."""
    return role in {"teacher", "headman"}


def can_manage_announcements(role: Optional[str]) -> bool:
    """Кто архивирует, восстанавливает, удаляет объявления."""
    return role in {"headman", "deputy_head", "dean", "admin"}


def can_manage_users(role: Optional[str]) -> bool:
    """Кто может добавлять и удалять сотрудников кафедры. Только администратор."""
    return role == "admin"


def humanize_size(size_bytes: Optional[int]) -> str:
    if not size_bytes:
        return ""
    units = ["Б", "КБ", "МБ", "ГБ"]
    s = float(size_bytes)
    for unit in units:
        if s < 1024 or unit == units[-1]:
            return f"{s:.0f} {unit}" if unit == "Б" else f"{s:.1f} {unit}"
        s /= 1024
    return ""
