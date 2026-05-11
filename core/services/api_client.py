"""
Клиент REST API кафедральной системы.
Бэкенд: FastAPI (модуль команды Риты), доступен по адресу из FASTAPI_API_BASE.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from django.conf import settings


TIMEOUT = 15


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

    detail = "Ошибка запроса к серверу"
    if isinstance(data, dict) and "detail" in data:
        if isinstance(data["detail"], list):
            detail = "; ".join(str(item) for item in data["detail"])
        else:
            detail = str(data["detail"])

    raise RuntimeError(detail)


def _url(path: str) -> str:
    return f"{settings.FASTAPI_API_BASE}{path}"


# ═══ Авторизация ═══════════════════════════════════════════════

def login_user(email: str, password: str) -> Dict[str, Any]:
    response = requests.post(
        _url("/auth/login"),
        data={"username": email, "password": password},
        timeout=TIMEOUT,
    )
    return _handle(response)


def logout_user(refresh_token: str) -> None:
    response = requests.post(
        _url("/auth/logout"),
        json={"refresh_token": refresh_token},
        timeout=TIMEOUT,
    )
    _handle(response)


def refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    response = requests.post(
        _url("/auth/refresh"),
        json={"refresh_token": refresh_token},
        timeout=TIMEOUT,
    )
    return _handle(response)


def get_current_user(token: str) -> Dict[str, Any]:
    response = requests.get(_url("/users/me"), headers=_headers(token), timeout=TIMEOUT)
    return _handle(response)


# ═══ Объявления ════════════════════════════════════════════════

def list_announcements(token: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    params = {"status": status} if status else None
    response = requests.get(
        _url("/announcements"), headers=_headers(token), params=params, timeout=TIMEOUT
    )
    return _handle(response) or []


def get_announcement(token: str, announcement_id: int) -> Dict[str, Any]:
    response = requests.get(
        _url(f"/announcements/{announcement_id}"),
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    return _handle(response)


# ═══ События ═══════════════════════════════════════════════════

def list_events(token: str) -> List[Dict[str, Any]]:
    response = requests.get(_url("/events"), headers=_headers(token), timeout=TIMEOUT)
    return _handle(response) or []


# ═══ Документы ═════════════════════════════════════════════════

def list_documents(token: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    params = {"category": category} if category else None
    response = requests.get(
        _url("/documents"), headers=_headers(token), params=params, timeout=TIMEOUT
    )
    return _handle(response) or []


def document_download_url(document_id: int) -> str:
    return _url(f"/documents/{document_id}/download")


# ═══ Состав ════════════════════════════════════════════════════

def list_staff(token: Optional[str] = None) -> List[Dict[str, Any]]:
    response = requests.get(
        _url("/users"),
        headers=_headers(token),
        params={"role_in": "teacher,dean,deputy_head"},
        timeout=TIMEOUT,
    )
    return _handle(response) or []


# ═══ Расписание / посещаемость / группы ════════════════════════

def list_groups(token: str) -> List[Dict[str, Any]]:
    response = requests.get(_url("/groups"), headers=_headers(token), timeout=TIMEOUT)
    return _handle(response) or []


def list_lessons(
    token: str, group_id: Optional[int] = None, week: Optional[str] = None
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if group_id:
        params["group_id"] = group_id
    if week:
        params["week"] = week
    response = requests.get(
        _url("/lessons"), headers=_headers(token), params=params, timeout=TIMEOUT
    )
    return _handle(response) or []


def list_attendance(token: str, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    params = {"user_id": user_id} if user_id else None
    response = requests.get(
        _url("/attendance"), headers=_headers(token), params=params, timeout=TIMEOUT
    )
    return _handle(response) or []


# ═══ Справочники для шаблонов ══════════════════════════════════

ROLE_LABELS = {
    "student":     "студент",
    "headman":     "староста",
    "teacher":     "преподаватель",
    "dean":        "заведующий кафедрой",
    "deputy_head": "заместитель заведующего",
    "admin":       "администратор",
}

CATEGORY_LABELS = {
    "order":    "приказ",
    "method":   "методическое",
    "vkr":      "темы ВКР",
    "template": "шаблон",
    "other":    "прочее",
}

ANNOUNCEMENT_STATUS_LABELS = {
    "draft":     "черновик",
    "scheduled": "запланировано",
    "published": "опубликовано",
    "archived":  "архив",
}


def can_create_content(role: Optional[str]) -> bool:
    return role in {"teacher", "dean", "deputy_head", "admin"}


def make_initials(full_name: str) -> str:
    if not full_name:
        return "·"
    parts = [p for p in full_name.split() if p]
    if len(parts) >= 2:
        return (parts[0][:1] + parts[1][:1]).upper()
    return parts[0][:2].upper() if parts else "·"


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
