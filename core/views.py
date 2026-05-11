"""
Представления (views) сайта кафедры СИИ.

Архитектура: Django выступает как BFF-слой (Backend For Frontend),
делегирующий все операции с данными в FastAPI-сервис команды.
JWT-токены хранятся в Django-сессии пользователя.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, Optional

import requests
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse

from .services import api_client as api


# ═══════════════════════════════════════════════════════════════
#  Утилиты сессии
# ═══════════════════════════════════════════════════════════════

def _get_token(request) -> Optional[str]:
    return request.session.get("access_token")


def _get_user(request) -> Optional[Dict[str, Any]]:
    return request.session.get("user")


def _set_session_user(request, user: Dict[str, Any]) -> None:
    """Кладёт сводку о пользователе прямо в сессию для шапки и авторизации."""
    full_name = " ".join(filter(None, [
        user.get("last_name", ""),
        user.get("first_name", ""),
    ])).strip() or user.get("email", "Пользователь")

    request.session["user"] = {
        **user,
        "full_name": full_name,
        "initials": api.make_initials(full_name),
        "role_label": api.ROLE_LABELS.get(user.get("role"), user.get("role", "пользователь")),
    }
    request.session["user_initial"] = api.make_initials(full_name)
    request.session["user_name"] = full_name.split()[0] if full_name else ""


def login_required_view(view_func: Callable) -> Callable:
    """Декоратор: редиректит на /login/, если нет токена."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not _get_token(request):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapped


def _safe_call(fn: Callable, *args, **kwargs) -> tuple[Any, Optional[str]]:
    """Безопасный вызов API: возвращает (data, error_message)."""
    try:
        return fn(*args, **kwargs), None
    except requests.RequestException:
        return None, "Не удалось подключиться к серверу. Попробуйте позже."
    except RuntimeError as exc:
        return None, str(exc)


# ═══════════════════════════════════════════════════════════════
#  Публичные страницы
# ═══════════════════════════════════════════════════════════════

def home_page(request):
    """Главная: hero + последние объявления + ближайшие события."""
    token = _get_token(request)
    announcements, events = [], []

    if token:
        anns_data, _ = _safe_call(api.list_announcements, token, status="published")
        if anns_data:
            announcements = anns_data[:3]

        events_data, _ = _safe_call(api.list_events, token)
        if events_data:
            events = []
            for item in events_data[:3]:
                image_url = item.get("image_url")
                item["image_full_url"] = (
                    f"{settings.FASTAPI_ROOT_URL}{image_url}" if image_url else None
                )
                events.append(item)

    return render(request, "pages/home.html", {
        "announcements": announcements,
        "events": events,
    })


def about_page(request):
    return render(request, "pages/about.html")


def staff_page(request):
    """Состав кафедры — может работать без токена (публичный список)."""
    token = _get_token(request)
    staff_data, error = _safe_call(api.list_staff, token)

    staff = []
    for person in staff_data or []:
        full_name = " ".join(filter(None, [
            person.get("last_name", ""),
            person.get("first_name", ""),
            person.get("middle_name", ""),
        ])).strip() or person.get("email", "")
        staff.append({
            **person,
            "full_name": full_name,
            "initials": api.make_initials(full_name),
            "position_label": api.ROLE_LABELS.get(person.get("role"), "Преподаватель"),
        })

    return render(request, "pages/staff.html", {"staff": staff, "error": error})


# ═══════════════════════════════════════════════════════════════
#  Авторизация
# ═══════════════════════════════════════════════════════════════

def login_page(request):
    if _get_token(request):
        return redirect("home")

    error: Optional[str] = None
    email = ""

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()

        if not email or not password:
            error = "Заполните e-mail и пароль."
        else:
            tokens, error = _safe_call(api.login_user, email, password)
            if tokens:
                request.session["access_token"] = tokens["access_token"]
                request.session["refresh_token"] = tokens.get("refresh_token", "")

                # Подтягиваем данные пользователя для шапки и кабинета
                user, _ = _safe_call(api.get_current_user, tokens["access_token"])
                if user:
                    _set_session_user(request, user)

                return redirect("home")

    return render(request, "pages/login.html", {"error": error, "email": email})


def logout_page(request):
    refresh_token = request.session.get("refresh_token")
    if refresh_token:
        _safe_call(api.logout_user, refresh_token)
    request.session.flush()
    return redirect("login")


@login_required_view
def profile_page(request):
    user = _get_user(request) or {}
    token = _get_token(request)

    recent, _ = _safe_call(api.list_announcements, token, status="published")
    return render(request, "pages/profile.html", {
        "user": user,
        "recent_announcements": (recent or [])[:5],
    })


# ═══════════════════════════════════════════════════════════════
#  Объявления
# ═══════════════════════════════════════════════════════════════

@login_required_view
def announcements_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}
    status = request.GET.get("status") or None

    items, error = _safe_call(api.list_announcements, token, status=status)
    return render(request, "pages/announcements.html", {
        "announcements": items or [],
        "current_status": status,
        "error": error,
        "can_create": api.can_create_content(user.get("role")),
    })


@login_required_view
def announcement_detail_page(request, announcement_id: int):
    token = _get_token(request)
    user = _get_user(request) or {}

    ann, error = _safe_call(api.get_announcement, token, announcement_id)
    return render(request, "pages/announcement_detail.html", {
        "announcement": ann or {},
        "error": error,
        "can_edit": api.can_create_content(user.get("role")),
    })


# ═══════════════════════════════════════════════════════════════
#  События
# ═══════════════════════════════════════════════════════════════

@login_required_view
def events_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}

    raw_events, error = _safe_call(api.list_events, token)
    events = []
    for item in raw_events or []:
        image_url = item.get("image_url")
        item["image_full_url"] = (
            f"{settings.FASTAPI_ROOT_URL}{image_url}" if image_url else None
        )
        events.append(item)

    return render(request, "pages/events.html", {
        "events": events,
        "error": error,
        "can_create": api.can_create_content(user.get("role")),
    })


# ═══════════════════════════════════════════════════════════════
#  Документы
# ═══════════════════════════════════════════════════════════════

@login_required_view
def documents_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}
    category = request.GET.get("category") or None

    raw_docs, error = _safe_call(api.list_documents, token, category=category)
    documents = []
    for item in raw_docs or []:
        item["download_url"] = api.document_download_url(item["id"])
        item["category_label"] = api.CATEGORY_LABELS.get(
            item.get("category"), item.get("category", "")
        )
        item["size_human"] = api.humanize_size(item.get("size"))
        documents.append(item)

    return render(request, "pages/documents.html", {
        "documents": documents,
        "current_category": category,
        "error": error,
        "can_upload": api.can_create_content(user.get("role")),
    })


# ═══════════════════════════════════════════════════════════════
#  Расписание
# ═══════════════════════════════════════════════════════════════

@login_required_view
def schedule_page(request):
    token = _get_token(request)
    week = request.GET.get("week", "odd")
    group_id = request.GET.get("group_id")

    groups, _ = _safe_call(api.list_groups, token)
    lessons, error = _safe_call(
        api.list_lessons,
        token,
        group_id=int(group_id) if group_id else None,
        week=week,
    )

    # Раскладываем занятия в сетку: 6 будних дней × 6 пар
    time_slots_template = [
        {"start": "08:30", "end": "10:00"},
        {"start": "10:15", "end": "11:45"},
        {"start": "12:15", "end": "13:45"},
        {"start": "14:00", "end": "15:30"},
        {"start": "15:45", "end": "17:15"},
        {"start": "17:30", "end": "19:00"},
    ]

    time_slots = []
    for slot_idx, slot in enumerate(time_slots_template):
        days = []
        for day_idx in range(6):  # пн–сб
            lesson = next(
                (
                    l for l in (lessons or [])
                    if l.get("slot_index") == slot_idx and l.get("day_of_week") == day_idx
                ),
                None,
            )
            days.append({"lesson": lesson})
        time_slots.append({**slot, "days": days})

    return render(request, "pages/schedule.html", {
        "groups": groups or [],
        "time_slots": time_slots if lessons else [],
        "current_week": week,
        "error": error,
    })


# ═══════════════════════════════════════════════════════════════
#  Посещаемость
# ═══════════════════════════════════════════════════════════════

@login_required_view
def attendance_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}

    reports, error = _safe_call(api.list_attendance, token)
    reports = reports or []

    # Сводная статистика для виджетов
    total = len(reports)
    present = sum(1 for r in reports if r.get("status") == "present")
    missed = sum(1 for r in reports if r.get("status") == "absent")
    excused = sum(1 for r in reports if r.get("status") == "excused")

    stats = {
        "present_count": present,
        "missed_count": missed,
        "excused_count": excused,
        "present_percent": round(present / total * 100) if total else 0,
    }

    role = user.get("role")
    return render(request, "pages/attendance.html", {
        "reports": reports,
        "stats": stats,
        "user_role": role,
        "can_generate_qr": api.can_create_content(role),
        "error": error,
    })


# ═══════════════════════════════════════════════════════════════
#  Обработчик 404
# ═══════════════════════════════════════════════════════════════

def not_found_page(request, exception=None):
    """Кастомная страница 404."""
    from django.shortcuts import render
    return render(request, "pages/404.html", status=404)
