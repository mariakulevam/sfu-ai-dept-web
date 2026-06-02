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


class TokenExpiredError(RuntimeError):
    """Access-токен недействителен или истёк (HTTP 401)."""
    pass


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

    # 401 — токен протух, отдельное исключение для авто-рефреша
    if response.status_code == 401:
        raise TokenExpiredError(detail)

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
                  group_id: int,
                  patronymic: Optional[str] = None) -> Dict[str, Any]:
    """POST /auth/register — регистрация студента.

    С новой версии backend требует group_id: студент сразу привязывается
    к учебной группе при регистрации. Роль фиксирована — student.
    """
    body = {
        "name": name,
        "surname": surname,
        "email": email,
        "password": password,
        "group_id": int(group_id),
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
    """GET /users/me — данные текущего пользователя с профилем по роли.

    Ответ зависит от роли: студент получает StudentMeResponse (с group_id,
    group_name, phone, telegram, vk), преподаватель — TeacherMeResponse
    (department, positions, phone, cabinet), декан/деканат — DeanMeResponse
    (faculty, position, phone, cabinet).
    """
    response = requests.get(
        _url("/users/me"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def reset_password(email: str) -> None:
    """POST /auth/reset-password — сброс пароля.

    Серверная часть генерирует новый пароль и отправляет его на email.
    Эндпоинт всегда возвращает 204 (даже если email не зарегистрирован),
    чтобы не раскрывать существование учётных записей.
    """
    response = requests.post(
        _url("/auth/reset-password"),
        json={"email": email},
        headers=_headers(json_body=True),
        timeout=TIMEOUT,
    )
    _handle(response)


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


def get_user(token: str, user_id: int) -> Optional[Dict[str, Any]]:
    """Получить данные пользователя по id.

    В новой версии backend эндпоинт GET /users/{id} убран: получить чужой
    профиль по идентификатору напрямую нельзя. Поэтому функция собирает данные
    из двух доступных источников:

    1. GET /users — список пользователей, видимых текущему (для студента это
       одногруппники + преподаватели; для преподавателя — его студенты + замзав;
       для админа/декана/замзав — все).
    2. GET /users/teachers — публичный список всех преподавателей кафедры.

    Результаты кэшируются на 60 секунд по токену, чтобы не дергать API на
    каждый рендер списка чатов или окна чата. Если пользователя не нашли —
    возвращается None, и фронт показывает заглушку «Пользователь #N».
    """
    cache = _user_cache_for(token)
    if user_id in cache:
        return cache[user_id]

    try:
        for u in list_users(token, limit=500) or []:
            cache[u["id"]] = u
    except Exception as exc:
        _logger.warning("get_user: list_users упал: %s", exc)

    if user_id not in cache:
        try:
            for t in list_teachers(token) or []:
                # схема TeacherPublicRead не содержит is_active/created_at и т.п.,
                # но нам достаточно name/surname/avatar/role для отображения.
                cache.setdefault(t["id"], t)
        except Exception as exc:
            _logger.warning("get_user: list_teachers упал: %s", exc)

    return cache.get(user_id)


# In-memory TTL-кэш пользователей: { token: { user_id: user_dict } }.
# Время жизни — 60 секунд, очищается при последующем запросе.
import time as _time
import logging as _logging
_logger = _logging.getLogger("kafedra.api_client")
_USER_CACHE: Dict[str, Dict[str, Any]] = {}
_USER_CACHE_TS: Dict[str, float] = {}
_USER_CACHE_TTL = 60.0  # секунд


def _user_cache_for(token: str) -> Dict[int, Dict[str, Any]]:
    key = token or ""
    now = _time.time()
    if now - _USER_CACHE_TS.get(key, 0) > _USER_CACHE_TTL:
        _USER_CACHE[key] = {}
        _USER_CACHE_TS[key] = now
    return _USER_CACHE[key]


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


def upload_avatar(token: str, file_path: str, file_name: str = "avatar.png",
                  mime_type: str = "image/png") -> Dict[str, Any]:
    """PATCH /users/me/avatar — прямая загрузка файла аватара.

    Серверная часть сохраняет файл локально и обновляет поле avatar
    у пользователя. Возвращает обновлённого пользователя (UserRead).
    """
    with open(file_path, "rb") as fh:
        files = {"file": (file_name, fh, mime_type)}
        response = requests.patch(
            _url("/users/me/avatar"),
            headers=_headers(token),
            files=files,
            timeout=TIMEOUT * 2,
        )
    return _handle(response)


def get_avatar_url(user_id: int) -> str:
    """Полный URL аватара пользователя для использования в <img src=...>.

    На бэкенде это GET /users/{id}/avatar, отдающий бинарный файл.
    Возвращаем URL — браузер сам отправит Authorization, если кука сессии
    есть, или фронт прокси-эндпоинт может проксировать запрос.
    """
    base = getattr(settings, "FASTAPI_PUBLIC_URL", settings.FASTAPI_ROOT_URL)
    return f"{base}/api/v1/users/{user_id}/avatar"


# ──────────────────────────────────────────────
# Профили (новые эндпоинты PATCH /users/me/{role}-profile)
# ──────────────────────────────────────────────

def update_student_profile(token: str, *, phone: Optional[str] = None,
                           telegram: Optional[str] = None,
                           vk: Optional[str] = None) -> Dict[str, Any]:
    """PATCH /users/me/student-profile — обновить контакты студента."""
    body: Dict[str, Any] = {}
    if phone is not None:
        body["phone"] = phone
    if telegram is not None:
        body["telegram"] = telegram
    if vk is not None:
        body["vk"] = vk
    response = requests.patch(
        _url("/users/me/student-profile"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def update_teacher_profile(token: str, *, department: Optional[str] = None,
                           positions: Optional[List[str]] = None,
                           phone: Optional[str] = None,
                           cabinet: Optional[str] = None) -> Dict[str, Any]:
    """PATCH /users/me/teacher-profile — обновить профиль преподавателя.

    positions — список TeacherPosition: assistant, lecturer, senior_lecturer,
    associate_professor, professor, sfu_professor, acting_head.
    """
    body: Dict[str, Any] = {}
    if department is not None:
        body["department"] = department
    if positions is not None:
        body["positions"] = positions
    if phone is not None:
        body["phone"] = phone
    if cabinet is not None:
        body["cabinet"] = cabinet
    response = requests.patch(
        _url("/users/me/teacher-profile"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def update_dean_profile(token: str, *, faculty: Optional[str] = None,
                        position: Optional[str] = None,
                        phone: Optional[str] = None,
                        cabinet: Optional[str] = None) -> Dict[str, Any]:
    """PATCH /users/me/dean-profile — обновить профиль деканата."""
    body: Dict[str, Any] = {}
    for k, v in (("faculty", faculty), ("position", position),
                 ("phone", phone), ("cabinet", cabinet)):
        if v is not None:
            body[k] = v
    response = requests.patch(
        _url("/users/me/dean-profile"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def update_user_group(token: str, user_id: int, group_id: int) -> None:
    """PATCH /users/{id}/group — изменить группу студента (admin/dean)."""
    response = requests.patch(
        _url(f"/users/{user_id}/group"),
        headers=_headers(token, json_body=True),
        json={"group_id": int(group_id)},
        timeout=TIMEOUT,
    )
    _handle(response)


# ──────────────────────────────────────────────
# Преподаватели, поиск, видимые пользователи
# ──────────────────────────────────────────────

def list_teachers(token: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /users/teachers — публичный список преподавателей кафедры.

    Возвращает TeacherPublicRead с полями: id, name, surname, patronymic,
    role, avatar, department, positions, cabinet. Используется на странице
    «Состав кафедры». Эндпоинт публичный, токен можно не передавать.
    """
    response = requests.get(
        _url("/users/teachers"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def search_users(token: str, surname: str,
                 limit: int = 20) -> List[Dict[str, Any]]:
    """GET /users/search?surname=... — поиск пользователя по фамилии.

    Доступен авторизованным пользователям; видимость подчиняется тем же
    правилам, что и GET /users (студент — одногруппники + преподаватели,
    преподаватель — свои студенты + замзав, admin/dean/deputy_head — все).
    """
    response = requests.get(
        _url("/users/search"),
        headers=_headers(token),
        params={"surname": surname, "limit": limit},
        timeout=TIMEOUT,
    )
    return _handle(response) or []


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


def list_my_announcements(token: str, status: Optional[str] = None,
                          skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
    """GET /announcements/my — объявления, относящиеся к текущему пользователю.

    Серверная часть сама решает, какие объявления показать (исходя из
    группы/потока студента, кафедры преподавателя и т.д.). Удобно для
    раздела «Мои объявления» в личном кабинете.
    """
    params: Dict[str, Any] = {"skip": skip, "limit": limit}
    if status:
        params["status"] = status
    response = requests.get(
        _url("/announcements/my"),
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    return _handle(response) or []


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


def get_event_image_url(event_id: int) -> str:
    """Полный URL картинки события для <img src=...>.

    Бэкенд отдаёт картинку через GET /events/{id}/image (бинарный поток).
    """
    base = getattr(settings, "FASTAPI_PUBLIC_URL", settings.FASTAPI_ROOT_URL)
    return f"{base}/api/v1/events/{event_id}/image"


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


def fetch_document_file(token: str, doc_id) -> tuple:
    """Скачивает файл документа с FastAPI. Возвращает (content_bytes, filename, content_type)."""
    response = requests.get(
        _url(f"/documents/{doc_id}/download"),
        headers=_headers(token),
        timeout=TIMEOUT * 3,
        stream=False,
    )
    if response.status_code == 401:
        raise TokenExpiredError("Токен истёк")
    if not response.ok:
        raise RuntimeError(f"Не удалось скачать документ (HTTP {response.status_code})")
    # Имя файла из заголовка Content-Disposition
    filename = f"document_{doc_id}"
    cd = response.headers.get("Content-Disposition", "")
    if "filename" in cd:
        import re as _re
        m = _re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
        if m:
            from urllib.parse import unquote
            filename = unquote(m.group(1))
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    return response.content, filename, content_type


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


def send_chat_message(token: str, chat_id: int, body: str) -> Dict[str, Any]:
    """POST /chats/{id}/messages — REST-альтернатива WebSocket-отправке.

    Используется как фолбэк, если WebSocket недоступен (например, при
    блокировке wss-портов в сети пользователя). Сервер сохраняет сообщение
    и рассылает его подключённым участникам через WebSocket.
    """
    response = requests.post(
        _url(f"/chats/{chat_id}/messages"),
        headers=_headers(token, json_body=True),
        json={"body": body},
        timeout=TIMEOUT,
    )
    return _handle(response)


def get_chat_ws_url(chat_id: int, access_token: str) -> str:
    """URL для WebSocket-подключения к чату.

    Использует публичный адрес (FASTAPI_PUBLIC_URL), т.к. подключение идёт
    из браузера пользователя, а не с сервера. На проде это wss://домен.
    """
    public = getattr(settings, "FASTAPI_PUBLIC_URL", settings.FASTAPI_ROOT_URL)
    base = public.replace("http://", "ws://").replace("https://", "wss://")
    return f"{base}/api/v1/chats/{chat_id}/ws?token={access_token}"


# ═══════════════════════════════════════════════════════════════
#  ВКР — /vkr/* (новый модуль)
# ═══════════════════════════════════════════════════════════════

def propose_vkr_topic(token: str, title: str,
                      description: Optional[str] = None) -> Dict[str, Any]:
    """POST /vkr/topics — предложить тему ВКР.

    Доступно: student, headman, teacher, deputy_head. Если предлагает
    студент или староста, в student_id автоматически проставляется его id
    (тема для самого себя). Если предлагает преподаватель или замзав —
    student_id остаётся пустым (общая тема для распределения).
    """
    body = {"title": title}
    if description:
        body["description"] = description
    response = requests.post(
        _url("/vkr/topics"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def list_my_vkr_topics(token: str) -> List[Dict[str, Any]]:
    """GET /vkr/my-topics — темы, предложенные текущим пользователем."""
    response = requests.get(
        _url("/vkr/my-topics"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def list_approved_vkr_topics(token: str) -> List[Dict[str, Any]]:
    """GET /vkr/topics/approved — одобренные темы (декан, замзав, админ)."""
    response = requests.get(
        _url("/vkr/topics/approved"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def list_all_vkr_topics(token: str,
                        status: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /vkr/topics?status=... — все темы с фильтром по статусу.

    Доступно только deputy_head и admin. status: pending|approved|rejected.
    """
    params: Dict[str, Any] = {}
    if status:
        params["status"] = status
    response = requests.get(
        _url("/vkr/topics"),
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    return _handle(response) or []


def get_vkr_topic(token: str, topic_id: int) -> Dict[str, Any]:
    """GET /vkr/topics/{id} — детали темы (привилегированные роли или автор)."""
    response = requests.get(
        _url(f"/vkr/topics/{topic_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


def review_vkr_topic(token: str, topic_id: int, *, approved: bool,
                     comment: Optional[str] = None) -> Dict[str, Any]:
    """POST /vkr/topics/{id}/review — одобрить или отклонить тему.

    Только deputy_head. При approved=False обязательно требуется comment
    (причина отклонения); серверная часть валидирует это.
    """
    body: Dict[str, Any] = {"approved": bool(approved)}
    if comment is not None:
        body["comment"] = comment
    response = requests.post(
        _url(f"/vkr/topics/{topic_id}/review"),
        headers=_headers(token, json_body=True),
        json=body,
        timeout=TIMEOUT,
    )
    return _handle(response)


def delete_vkr_topics(token: str,
                      ids: Optional[List[int]] = None) -> None:
    """DELETE /vkr/topics?ids=1&ids=2 — удалить темы (deputy_head/admin).

    Без параметра ids удаляются ВСЕ темы — функция используется
    исключительно в админских сценариях очистки.
    """
    params: Dict[str, Any] = {}
    if ids:
        params["ids"] = list(map(int, ids))
    response = requests.delete(
        _url("/vkr/topics"),
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    _handle(response)


VKR_STATUS_LABELS = {
    "pending":  "на рассмотрении",
    "approved": "одобрено",
    "rejected": "отклонено",
}

VKR_STATUS_BADGES = {
    "pending":  "warning",
    "approved": "success",
    "rejected": "danger",
}


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


def can_create_announcement(role: Optional[str]) -> bool:
    """POST /announcements — headman, teacher, deputy_head, dean, admin."""
    return role in {"headman", "teacher", "deputy_head", "dean", "admin"}


def can_archive_announcement(role: Optional[str]) -> bool:
    """PATCH /announcements/{id}/archive — headman, deputy_head, dean, admin."""
    return role in {"headman", "deputy_head", "dean", "admin"}


def can_restore_announcement(role: Optional[str]) -> bool:
    """PATCH /announcements/{id}/restore — только dean, admin."""
    return role in {"dean", "admin"}


def can_create_event(role: Optional[str]) -> bool:
    """POST /events — headman, teacher, deputy_head, dean, admin."""
    return role in {"headman", "teacher", "deputy_head", "dean", "admin"}


def can_upload_documents(role: Optional[str]) -> bool:
    """POST /documents — teacher, deputy_head, dean, admin (без headman!)."""
    return role in {"teacher", "deputy_head", "dean", "admin"}


def can_manage_attendance(role: Optional[str]) -> bool:
    """POST /attendance/token и /attendance/manual — teacher, headman, deputy_head."""
    return role in {"teacher", "headman", "deputy_head"}


def can_scan_qr(role: Optional[str]) -> bool:
    """POST /attendance/scan/{token} — только student и headman."""
    return role in {"student", "headman"}


def can_send_messages(role: Optional[str]) -> bool:
    """POST /messages — headman, teacher, deputy_head, admin."""
    return role in {"headman", "teacher", "deputy_head", "admin"}


def can_sync_lessons(role: Optional[str]) -> bool:
    """POST /lessons/sync — только dean, admin."""
    return role in {"dean", "admin"}


def can_manage_groups_streams(role: Optional[str]) -> bool:
    """POST/PATCH/DELETE /groups и /streams — dean, admin."""
    return role in {"dean", "admin"}


def can_assign_student_group(role: Optional[str]) -> bool:
    """PATCH /users/{id}/group — только dean."""
    return role == "dean"


def can_manage_users(role: Optional[str]) -> bool:
    """POST/DELETE /users — только admin."""
    return role == "admin"


def can_propose_vkr_topic(role: Optional[str]) -> bool:
    """POST /vkr/topics — student, headman, teacher, deputy_head."""
    return role in {"student", "headman", "teacher", "deputy_head"}


def can_review_vkr_topics(role: Optional[str]) -> bool:
    """POST /vkr/topics/{id}/review — только deputy_head."""
    return role == "deputy_head"


def can_view_all_vkr_topics(role: Optional[str]) -> bool:
    """GET /vkr/topics — deputy_head, admin."""
    return role in {"deputy_head", "admin"}


def can_view_approved_vkr_topics(role: Optional[str]) -> bool:
    """GET /vkr/topics/approved — deputy_head, dean, admin."""
    return role in {"deputy_head", "dean", "admin"}


# ── Алиасы для обратной совместимости с уже написанными view-функциями ──

def can_create_content(role: Optional[str]) -> bool:
    """Алиас: общий флаг «может создавать объявления или события»."""
    return can_create_announcement(role) or can_create_event(role)


def can_manage_announcements(role: Optional[str]) -> bool:
    """Алиас: общий флаг «может управлять объявлениями» (для шапки/меню)."""
    return can_create_announcement(role) or can_archive_announcement(role)


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
