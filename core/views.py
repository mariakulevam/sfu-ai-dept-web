"""
Представления (views) сайта кафедры СИИ.

Архитектура: Django выступает как BFF-слой (Backend For Frontend),
делегирующий все операции с данными в FastAPI-сервис команды.
JWT-токены хранятся в Django-сессии пользователя.

Согласован с REST API v1.0 (см. backend/README.md, ARCHITECTURE.md).
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

import requests
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, Http404
from django.views.decorators.http import require_POST

from .services import api_client as api


# ═══════════════════════════════════════════════════════════════
#  Утилиты сессии
# ═══════════════════════════════════════════════════════════════

def _get_token(request) -> Optional[str]:
    return request.session.get("access_token")


def _get_user(request) -> Optional[Dict[str, Any]]:
    return request.session.get("user")


def _set_session_user(request, user: Dict[str, Any]) -> None:
    """Кладёт обогащённую сводку пользователя в сессию для шапки/прав."""
    fn = api.full_name(user)
    sn = api.short_name(user)

    # Серверный аватар: путь к файлу относительно api-сервера
    avatar_path = user.get("avatar")
    avatar_url = api.get_media_url(avatar_path)

    # Имя группы — если есть student_profile с group
    group_name = None
    sp = user.get("student_profile") or user.get("student_profiles")
    if isinstance(sp, dict):
        gr = sp.get("group")
        if isinstance(gr, dict):
            group_name = gr.get("name")

    request.session["user"] = {
        **user,
        "full_name": fn,
        "short_name": sn,
        "initials": api.make_initials(user),
        "role_label": api.ROLE_LABELS.get(user.get("role"), user.get("role", "пользователь")),
        "avatar_url": avatar_url,
        "group_name": group_name,
        "can_create_content": api.can_create_content(user.get("role")),
        "can_upload_documents": api.can_upload_documents(user.get("role")),
        "can_manage_attendance": api.can_manage_attendance(user.get("role")),
        "can_manage_announcements": api.can_manage_announcements(user.get("role")),
        "can_manage_users": api.can_manage_users(user.get("role")),
    }


def login_required_view(view_func: Callable) -> Callable:
    """Декоратор: редиректит на /login/, если нет токена."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not _get_token(request):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapped


import logging
_logger = logging.getLogger("kafedra.token")


def _refresh_access_token(request) -> Optional[str]:
    """Пытается обновить access-токен через refresh. Возвращает новый токен или None."""
    refresh = request.session.get("refresh_token")
    if not refresh:
        _logger.warning("REFRESH: в сессии нет refresh_token — рефрешить нечем")
        return None
    try:
        tokens = api.refresh_tokens(refresh)
    except Exception as exc:
        _logger.warning("REFRESH: /auth/refresh упал: %s", exc)
        return None
    new_access = tokens.get("access_token")
    new_refresh = tokens.get("refresh_token")
    if new_access:
        request.session["access_token"] = new_access
        if new_refresh:
            request.session["refresh_token"] = new_refresh
        request.session.modified = True
        _logger.info("REFRESH: токен успешно обновлён")
        return new_access
    _logger.warning("REFRESH: /auth/refresh вернул ответ без access_token: %s", tokens)
    return None


def _safe_call(request_or_fn, *args, **kwargs):
    """Безопасный вызов API: возвращает (data, error_message).

    Поддерживает два режима:
      _safe_call(request, api.func, ...)            — старый стиль, без авто-рефреша
      _safe_call(request, api.func, token, ...) — с авто-рефрешем токена при 401

    Авто-рефреш срабатывает если первым аргументом передан request (имеет .session).
    """
    # Определяем режим
    if hasattr(request_or_fn, "session"):
        request = request_or_fn
        fn = args[0]
        call_args = list(args[1:])
    else:
        request = None
        fn = request_or_fn
        call_args = list(args)

    try:
        return fn(*call_args, **kwargs), None
    except requests.RequestException:
        return None, "Не удалось подключиться к серверу. Попробуйте позже."
    except api.TokenExpiredError as exc:
        # Пытаемся обновить токен и повторить — только если есть request
        if request is not None:
            old_token = request.session.get("access_token")
            new_token = _refresh_access_token(request)
            if new_token:
                # Подменяем старый access-токен на новый в аргументах вызова
                new_args = [
                    new_token if (isinstance(a, str) and a == old_token) else a
                    for a in call_args
                ]
                # Если совпадения не нашлось — заменяем первый строковый аргумент
                if new_args == call_args and call_args and isinstance(call_args[0], str):
                    new_args[0] = new_token
                try:
                    return fn(*new_args, **kwargs), None
                except requests.RequestException:
                    return None, "Не удалось подключиться к серверу. Попробуйте позже."
                except api.TokenExpiredError:
                    return None, "Сессия истекла. Войдите заново."
                except RuntimeError as exc2:
                    return None, str(exc2)
        return None, str(exc)
    except RuntimeError as exc:
        return None, str(exc)


def _make_image_full_url(item: Dict[str, Any]) -> Dict[str, Any]:
    """Дополняет item полем image_full_url, если есть image_url."""
    img = item.get("image_url")
    item["image_full_url"] = (
        f"{settings.FASTAPI_ROOT_URL}{img}" if img else None
    )
    return item


# ═══════════════════════════════════════════════════════════════
#  Публичные страницы
# ═══════════════════════════════════════════════════════════════

def home_page(request):
    """Главная: hero + последние объявления + ближайшие события."""
    token = _get_token(request)
    announcements, events = [], []

    # Авторизованный — показываем актуальные данные из API
    if token:
        anns, _ = _safe_call(request, api.list_announcements, token, status="published", limit=3)
        announcements = anns or []

        events_data, _ = _safe_call(request, api.list_events, token)
        events = [_make_image_full_url(e) for e in (events_data or [])[:3]]

    return render(request, "pages/home.html", {
        "announcements": announcements,
        "events": events,
    })


def about_page(request):
    return render(request, "pages/about.html")


def programs_page(request):
    return render(request, "pages/programs.html")


@login_required_view
def manage_staff_page(request):
    """Управление составом кафедры — добавление и удаление сотрудников. Только admin."""
    token = _get_token(request)
    user = _get_user(request) or {}

    if not api.can_manage_users(user.get("role")):
        return redirect("staff")

    form_error: Optional[str] = None
    form_success: Optional[str] = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        # ── Добавление сотрудника ──
        if action == "add_staff":
            name = request.POST.get("name", "").strip()
            surname = request.POST.get("surname", "").strip()
            patronymic = request.POST.get("patronymic", "").strip()
            email = request.POST.get("email", "").strip()
            role = request.POST.get("role", "teacher")

            if not name or not surname:
                form_error = "Заполните имя и фамилию"
            elif not email:
                form_error = "Укажите e-mail"
            elif role not in {"teacher", "dean", "deputy_head", "headman"}:
                form_error = "Недопустимая роль"
            else:
                _, err = _safe_call(
                    request, api.admin_create_user, token,
                    name, surname, email, role,
                    patronymic=patronymic or None,
                )
                if err:
                    form_error = err
                else:
                    form_success = (
                        f"Сотрудник {surname} {name} добавлен. "
                        f"Пароль для входа отправлен на {email}"
                    )

        # ── Удаление сотрудника ──
        elif action == "delete_staff":
            user_id = request.POST.get("user_id")
            if user_id and user_id.isdigit():
                _, err = _safe_call(request, api.delete_user, token, int(user_id))
                if err:
                    form_error = err
                else:
                    form_success = "Сотрудник удалён"

    # Текущий список сотрудников
    users_data, error = _safe_call(request, api.list_users, token, limit=200)
    staff = []
    for u in users_data or []:
        role = u.get("role")
        if role not in {"teacher", "deputy_head", "dean", "headman"}:
            continue
        staff.append({
            **u,
            "full_name": api.full_name(u),
            "role_label": api.ROLE_LABELS.get(role, role),
        })
    staff.sort(key=lambda x: x.get("surname") or "")

    return render(request, "pages/manage_staff.html", {
        "staff": staff,
        "form_error": form_error,
        "form_success": form_success,
        "load_error": error,
    })


def staff_page(request):
    """Состав кафедры — только для авторизованных (API требует токен)."""
    token = _get_token(request)
    if not token:
        return render(request, "pages/staff.html", {
            "staff": [],
            "error": "Войдите в систему, чтобы увидеть список сотрудников.",
            "require_login": True,
        })

    users_data, error = _safe_call(request, api.list_users, token, limit=200)
    staff = []

    # Иерархия должностей — для сортировки и отображения «главной» должности
    POSITION_RANK = {
        "acting_head":         0,
        "professor":           1,
        "sfu_professor":       2,
        "associate_professor": 3,
        "senior_lecturer":     4,
        "lecturer":            5,
        "assistant":           6,
    }
    ROLE_RANK = {"dean": 0, "deputy_head": 1, "teacher": 2}

    for u in users_data or []:
        role = u.get("role")
        # На странице «Состав» показываем только преподавателей и руководство
        if role not in {"teacher", "deputy_head", "dean"}:
            continue

        profile = u.get("teacher_profile") or {}
        dean_profile = u.get("dean_profile") or {}
        positions = profile.get("positions") or []

        # Находим «главную» должность (с наименьшим рангом)
        main_position = None
        if positions:
            main_position = sorted(
                positions,
                key=lambda p: POSITION_RANK.get(p, 99),
            )[0]

        # Для роли dean показываем «заведующий кафедрой» вместо обычной должности
        if role == "dean":
            position_label = dean_profile.get("position") or "Заведующий кафедрой"
        elif role == "deputy_head":
            position_label = "Заместитель заведующего кафедрой"
        else:
            position_label = api.TEACHER_POSITION_LABELS.get(main_position, "Преподаватель")

        person = {
            **u,
            "full_name": api.full_name(u),
            "initials": api.make_initials(u),
            "role_label": api.ROLE_LABELS.get(role, role),
            "position_label": position_label,
            "all_positions": [api.TEACHER_POSITION_LABELS.get(p, p) for p in positions],
            "cabinet": profile.get("cabinet") or dean_profile.get("cabinet"),
            "phone": profile.get("phone") or dean_profile.get("phone"),
            "department": profile.get("department") or dean_profile.get("faculty"),
            "avatar_url": api.get_media_url(u.get("avatar")),
            "_sort_key": (ROLE_RANK.get(role, 9), POSITION_RANK.get(main_position, 99)),
        }
        staff.append(person)

    # Сортируем: сначала dean, потом deputy_head, потом преподаватели по должности
    staff.sort(key=lambda x: x["_sort_key"])

    return render(request, "pages/staff.html", {
        "staff": staff,
        "error": error,
    })


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
            tokens, error = _safe_call(request, api.login_user, email, password)
            if tokens:
                request.session["access_token"] = tokens["access_token"]
                request.session["refresh_token"] = tokens.get("refresh_token", "")

                # Подтягиваем профиль пользователя
                user, _ = _safe_call(request, api.get_current_user, tokens["access_token"])
                if user:
                    _set_session_user(request, user)

                return redirect("home")

    return render(request, "pages/login.html", {"error": error, "email": email})


def logout_page(request):
    refresh_token = request.session.get("refresh_token")
    if refresh_token:
        _safe_call(request, api.logout_user, refresh_token)
    request.session.flush()
    return redirect("login")


def register_page(request):
    """Регистрация нового пользователя (роль автоматически student)."""
    if _get_token(request):
        return redirect("home")

    error: Optional[str] = None
    form_data = {"name": "", "surname": "", "patronymic": "", "email": ""}

    if request.method == "POST":
        form_data["name"] = request.POST.get("name", "").strip()
        form_data["surname"] = request.POST.get("surname", "").strip()
        form_data["patronymic"] = request.POST.get("patronymic", "").strip()
        form_data["email"] = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")

        if not form_data["name"] or not form_data["surname"]:
            error = "Заполните имя и фамилию."
        elif not form_data["email"]:
            error = "Укажите e-mail."
        elif not password:
            error = "Придумайте пароль."
        elif len(password) < 6:
            error = "Пароль должен быть не короче 6 символов."
        elif password != confirm:
            error = "Пароль и подтверждение не совпадают."
        else:
            _, err = _safe_call(
                request, api.register_user,
                form_data["name"],
                form_data["surname"],
                form_data["email"],
                password,
                patronymic=form_data["patronymic"] or None,
            )
            if err:
                error = err
            else:
                # Регистрация прошла — сразу логиним пользователя
                tokens, login_err = _safe_call(request, api.login_user, form_data["email"], password)
                if tokens:
                    request.session["access_token"] = tokens["access_token"]
                    request.session["refresh_token"] = tokens.get("refresh_token", "")
                    user, _ = _safe_call(request, api.get_current_user, tokens["access_token"])
                    if user:
                        _set_session_user(request, user)
                    return redirect("home")
                # Если автологин не сработал — отправляем на форму входа
                return redirect("login")

    return render(request, "pages/register.html", {"error": error, "form": form_data})


@login_required_view
def profile_page(request):
    """Личный кабинет — профиль + смена пароля + аватар + редактирование."""
    user = _get_user(request) or {}
    token = _get_token(request)

    password_error: Optional[str] = None
    password_success: Optional[str] = None
    profile_error: Optional[str] = None
    profile_success: Optional[str] = None
    avatar_error: Optional[str] = None
    avatar_success: Optional[str] = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        # ── Смена пароля ──
        if action == "change_password":
            old = request.POST.get("old_password", "")
            new = request.POST.get("new_password", "")
            confirm = request.POST.get("confirm_password", "")

            if not old or not new:
                password_error = "Заполните оба поля"
            elif new != confirm:
                password_error = "Новый пароль и подтверждение не совпадают"
            elif len(new) < 6:
                password_error = "Пароль должен быть не короче 6 символов"
            else:
                _, err = _safe_call(request, api.change_password, token, user.get("id"), old, new)
                if err:
                    password_error = err
                else:
                    password_success = "Пароль успешно изменён"

        # ── Редактирование профиля (имя, email) ──
        elif action == "update_profile":
            new_name = request.POST.get("name", "").strip()
            new_surname = request.POST.get("surname", "").strip()
            new_patronymic = request.POST.get("patronymic", "").strip()
            new_email = request.POST.get("email", "").strip()

            payload = {}
            if new_name and new_name != user.get("name"):
                payload["name"] = new_name
            if new_surname and new_surname != user.get("surname"):
                payload["surname"] = new_surname
            if new_patronymic != (user.get("patronymic") or ""):
                payload["patronymic"] = new_patronymic
            if new_email and new_email != user.get("email"):
                payload["email"] = new_email

            if not payload:
                profile_error = "Изменений нет"
            else:
                updated, err = _safe_call(request, api.update_user, token, user.get("id"), payload)
                if err:
                    profile_error = err
                else:
                    _set_session_user(request, updated)
                    user = updated
                    profile_success = "Изменения сохранены"

        # ── Загрузка аватара ──
        elif action == "upload_avatar":
            avatar_file = request.FILES.get("avatar")
            if not avatar_file:
                avatar_error = "Файл не выбран"
            elif avatar_file.size > 2 * 1024 * 1024:
                avatar_error = "Размер файла не более 2 МБ"
            else:
                import tempfile, os
                # Сохраняем во временный файл
                tmp_dir = tempfile.gettempdir()
                tmp_path = os.path.join(tmp_dir, avatar_file.name)
                with open(tmp_path, "wb") as f:
                    for chunk in avatar_file.chunks():
                        f.write(chunk)
                try:
                    updated, err = _safe_call(request, api.upload_avatar, token, tmp_path, avatar_file.name)
                    if err:
                        avatar_error = err
                    else:
                        _set_session_user(request, updated)
                        user = updated
                        avatar_success = "Аватар обновлён"
                finally:
                    try: os.remove(tmp_path)
                    except OSError: pass

    recent_announcements, _ = _safe_call(request, api.list_announcements, token, status="published", limit=5)

    return render(request, "pages/profile.html", {
        "user": user,
        "recent_announcements": recent_announcements or [],
        "password_error": password_error,
        "password_success": password_success,
        "profile_error": profile_error,
        "profile_success": profile_success,
        "avatar_error": avatar_error,
        "avatar_success": avatar_success,
    })


# ═══════════════════════════════════════════════════════════════
#  Объявления
# ═══════════════════════════════════════════════════════════════

@login_required_view
def announcements_page(request):
    """Список объявлений."""
    token = _get_token(request)
    user = _get_user(request) or {}
    status_filter = request.GET.get("status") or None

    items, error = _safe_call(request, api.list_announcements, token, status=status_filter)
    enriched = []
    for a in items or []:
        st = a.get("status")
        a["status_label"] = api.ANNOUNCEMENT_STATUS_LABELS.get(st, st)
        a["status_badge"] = api.ANNOUNCEMENT_STATUS_BADGES.get(st, "neutral")
        enriched.append(a)

    return render(request, "pages/announcements.html", {
        "announcements": enriched,
        "current_status": status_filter,
        "error": error,
        "can_create": api.can_create_content(user.get("role")),
        "can_manage": api.can_manage_announcements(user.get("role")),
    })


@login_required_view
def announcement_detail_page(request, announcement_id: int):
    """Карточка объявления."""
    token = _get_token(request)
    user = _get_user(request) or {}

    ann, error = _safe_call(request, api.get_announcement, token, announcement_id)
    if ann:
        st = ann.get("status")
        ann["status_label"] = api.ANNOUNCEMENT_STATUS_LABELS.get(st, st)
        ann["status_badge"] = api.ANNOUNCEMENT_STATUS_BADGES.get(st, "neutral")
        # URL для скачивания вложений
        for att in ann.get("attachments", []) or []:
            att["size_human"] = api.humanize_size(att.get("size_bytes"))

    return render(request, "pages/announcement_detail.html", {
        "announcement": ann or {},
        "error": error,
        "user": user,
        "can_manage": api.can_manage_announcements(user.get("role")),
        "is_author": ann and user and ann.get("author_id") == user.get("id"),
    })


@login_required_view
def announcement_create_page(request):
    """Создание нового объявления."""
    token = _get_token(request)
    user = _get_user(request) or {}
    if not api.can_create_content(user.get("role")):
        return redirect("announcements")

    error: Optional[str] = None
    form_data: Dict[str, Any] = {}

    # Подгружаем справочники групп и потоков для адресации
    groups_data, _ = _safe_call(request, api.list_groups, token)
    streams_data, _ = _safe_call(request, api.list_streams, token)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        content = request.POST.get("content", "").strip()
        group_ids = [int(g) for g in request.POST.getlist("group_ids") if g.isdigit()]
        stream_ids = [int(s) for s in request.POST.getlist("stream_ids") if s.isdigit()]
        publish_at = request.POST.get("publish_at") or None
        expires_at = request.POST.get("expires_at") or None

        form_data = {
            "title": title, "content": content,
            "group_ids": group_ids, "stream_ids": stream_ids,
            "publish_at": publish_at, "expires_at": expires_at,
        }

        if not title or not content:
            error = "Заполните заголовок и текст объявления."
        else:
            created, err = _safe_call(
                request, api.create_announcement, token,
                title=title, content=content,
                target_group_ids=group_ids or None,
                target_stream_ids=stream_ids or None,
                publish_at=publish_at, expires_at=expires_at,
            )
            if err:
                error = err
            elif created:
                return redirect("announcement_detail", announcement_id=created["id"])

    return render(request, "pages/announcement_form.html", {
        "groups": groups_data or [],
        "streams": streams_data or [],
        "error": error,
        "form": form_data,
        "form_title": "Новое объявление",
        "submit_label": "Опубликовать",
    })


@login_required_view
def announcement_edit_page(request, announcement_id: int):
    """Редактирование объявления (headman, deputy_head, dean)."""
    token = _get_token(request)
    user = _get_user(request) or {}
    if not api.can_manage_announcements(user.get("role")):
        return redirect("announcement_detail", announcement_id=announcement_id)

    error: Optional[str] = None

    # Текущее объявление
    ann, load_err = _safe_call(request, api.get_announcement, token, announcement_id)
    if load_err or not ann:
        raise Http404("Объявление не найдено")

    groups_data, _ = _safe_call(request, api.list_groups, token)
    streams_data, _ = _safe_call(request, api.list_streams, token)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        content = request.POST.get("content", "").strip()
        group_ids = [int(g) for g in request.POST.getlist("group_ids") if g.isdigit()]
        stream_ids = [int(s) for s in request.POST.getlist("stream_ids") if s.isdigit()]
        publish_at = request.POST.get("publish_at") or None
        expires_at = request.POST.get("expires_at") or None

        if not title or not content:
            error = "Заполните заголовок и текст объявления."
        else:
            payload = {
                "title": title,
                "content": content,
                "target_group_ids": group_ids or None,
                "target_stream_ids": stream_ids or None,
                "publish_at": publish_at,
                "expires_at": expires_at,
            }
            updated, err = _safe_call(request, api.update_announcement, token, announcement_id, payload)
            if err:
                error = err
            elif updated:
                return redirect("announcement_detail", announcement_id=announcement_id)
        # при ошибке — показываем введённое
        ann = {**ann, "title": title, "content": content}

    # Предзаполнение выбранных групп/потоков
    selected_group_ids = [g.get("id") for g in (ann.get("target_groups") or [])]
    selected_stream_ids = [s.get("id") for s in (ann.get("target_streams") or [])]

    return render(request, "pages/announcement_form.html", {
        "groups": groups_data or [],
        "streams": streams_data or [],
        "error": error,
        "form": {
            "title": ann.get("title", ""),
            "content": ann.get("content", ""),
            "group_ids": selected_group_ids,
            "stream_ids": selected_stream_ids,
            "publish_at": (ann.get("publish_at") or "")[:16],
            "expires_at": (ann.get("expires_at") or "")[:16],
        },
        "form_title": "Редактировать объявление",
        "submit_label": "Сохранить",
        "is_edit": True,
        "announcement_id": announcement_id,
    })


@login_required_view
@require_POST
def announcement_archive(request, announcement_id: int):
    token = _get_token(request)
    _, err = _safe_call(request, api.archive_announcement, token, announcement_id)
    if err:
        # Можно показать flash-сообщение, но проще просто редирект назад
        pass
    return redirect("announcements")


@login_required_view
@require_POST
def announcement_restore(request, announcement_id: int):
    token = _get_token(request)
    _safe_call(request, api.restore_announcement, token, announcement_id)
    return redirect("announcement_detail", announcement_id=announcement_id)


@login_required_view
@require_POST
def announcement_delete(request, announcement_id: int):
    token = _get_token(request)
    _safe_call(request, api.delete_announcement, token, announcement_id)
    return redirect("announcements")


# ═══════════════════════════════════════════════════════════════
#  События
# ═══════════════════════════════════════════════════════════════

@login_required_view
def events_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}

    raw_events, error = _safe_call(request, api.list_events, token)
    events = [_make_image_full_url(e) for e in (raw_events or [])]

    return render(request, "pages/events.html", {
        "events": events,
        "error": error,
        "can_create": api.can_create_content(user.get("role")),
    })


@login_required_view
def event_create_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}
    if not api.can_create_content(user.get("role")):
        return redirect("events")

    rooms_data, _ = _safe_call(request, api.list_rooms, token)
    error: Optional[str] = None
    form_data: Dict[str, Any] = {}

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        annotation = request.POST.get("annotation", "").strip()
        starts_at = request.POST.get("starts_at", "").strip()
        ends_at = request.POST.get("ends_at", "").strip()
        room_id = request.POST.get("room_id") or None
        if room_id and not room_id.isdigit():
            room_id = None
        room_id = int(room_id) if room_id else None

        form_data = {
            "title": title, "annotation": annotation,
            "starts_at": starts_at, "ends_at": ends_at,
            "room_id": room_id,
        }

        if not title or not starts_at or not ends_at:
            error = "Заполните название, дату начала и дату окончания."
        else:
            created, err = _safe_call(
                request, api.create_event, token,
                title=title, starts_at=starts_at, ends_at=ends_at,
                annotation=annotation or None, room_id=room_id,
            )
            if err:
                error = err
            elif created:
                return redirect("events")

    return render(request, "pages/event_form.html", {
        "rooms": rooms_data or [],
        "error": error,
        "form": form_data,
        "form_title": "Новое событие",
        "submit_label": "Создать",
    })


@login_required_view
def event_edit_page(request, event_id: int):
    """Редактирование события (teacher, headman, admin)."""
    token = _get_token(request)
    user = _get_user(request) or {}
    if not api.can_create_content(user.get("role")):
        return redirect("events")

    event, load_err = _safe_call(request, api.get_event, token, event_id)
    if load_err or not event:
        raise Http404("Событие не найдено")

    rooms_data, _ = _safe_call(request, api.list_rooms, token)
    error: Optional[str] = None

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        annotation = request.POST.get("annotation", "").strip()
        starts_at = request.POST.get("starts_at", "").strip()
        ends_at = request.POST.get("ends_at", "").strip()
        room_id = request.POST.get("room_id") or None
        if room_id and not room_id.isdigit():
            room_id = None
        room_id = int(room_id) if room_id else None

        if not title or not starts_at or not ends_at:
            error = "Заполните название, дату начала и дату окончания."
        else:
            payload = {
                "title": title,
                "annotation": annotation or None,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "room_id": room_id,
            }
            updated, err = _safe_call(request, api.update_event, token, event_id, payload)
            if err:
                error = err
            elif updated:
                return redirect("events")
        event = {**event, "title": title, "annotation": annotation,
                 "starts_at": starts_at, "ends_at": ends_at, "room_id": room_id}

    return render(request, "pages/event_form.html", {
        "rooms": rooms_data or [],
        "error": error,
        "form": {
            "title": event.get("title", ""),
            "annotation": event.get("annotation", ""),
            "starts_at": (event.get("starts_at") or "")[:16],
            "ends_at": (event.get("ends_at") or "")[:16],
            "room_id": event.get("room_id"),
        },
        "form_title": "Редактировать событие",
        "submit_label": "Сохранить",
        "is_edit": True,
        "event_id": event_id,
    })


@login_required_view
@require_POST
def event_delete(request, event_id: int):
    token = _get_token(request)
    _safe_call(request, api.delete_event, token, event_id)
    return redirect("events")


# ═══════════════════════════════════════════════════════════════
#  Документы
# ═══════════════════════════════════════════════════════════════

@login_required_view
def documents_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}
    category = request.GET.get("category") or None

    raw_docs, error = _safe_call(request, api.list_documents, token)
    documents = []
    for d in raw_docs or []:
        if category and d.get("category") != category:
            continue
        # Скачивание идёт через Django (он добавит JWT-токен), не напрямую на FastAPI
        d["download_url"] = reverse("document_download", args=[d["id"]])
        d["category_label"] = api.CATEGORY_LABELS.get(
            d.get("category"), d.get("category", "")
        )
        documents.append(d)

    return render(request, "pages/documents.html", {
        "documents": documents,
        "current_category": category,
        "error": error,
        "can_upload": api.can_upload_documents(user.get("role")),
    })


@login_required_view
def document_download(request, doc_id):
    """Прокси-скачивание документа: Django качает файл с FastAPI с токеном и отдаёт пользователю."""
    token = _get_token(request)
    result, error = _safe_call(request, api.fetch_document_file, token, doc_id)
    if error or not result:
        raise Http404(error or "Документ не найден")
    content, filename, content_type = result

    response = HttpResponse(content, content_type=content_type)
    # inline для просмотра в браузере (PDF/картинки откроются), скачивание — через download-атрибут в шаблоне
    from urllib.parse import quote
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(filename)}"
    return response


# ═══════════════════════════════════════════════════════════════
#  Расписание — /lessons/group/{id} | /lessons/teacher/{id}
# ═══════════════════════════════════════════════════════════════

@login_required_view
def schedule_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}
    user_role = user.get("role")

    # Определение источника расписания
    # week может быть: None (по умолчанию), 'current', 'both', '1' (нечётная), '2' (чётная)
    week_param = request.GET.get("week")
    week_filter: Optional[int] = None  # что отправляем в API (1, 2 или None)
    week_label = None  # что показываем в UI

    if week_param == "current":
        # Текущая неделя — высчитываем чётность по номеру недели в году от 1 февраля
        from datetime import date
        today = date.today()
        # Условно: семестр стартует с 1 сентября, недели чередуются с этой даты
        if today.month >= 9:
            start = date(today.year, 9, 1)
        elif today.month >= 2:
            start = date(today.year, 2, 1)
        else:
            start = date(today.year - 1, 9, 1)
        diff_weeks = ((today - start).days // 7)
        # Нечётная (week=1) если diff_weeks чётный, иначе чётная (week=2)
        week_filter = 1 if diff_weeks % 2 == 0 else 2
        week_label = "current"
    elif week_param == "both":
        week_filter = None  # без фильтра — обе недели
        week_label = "both"
    elif week_param in ("1", "2"):
        week_filter = int(week_param)
        week_label = week_filter
    else:
        week_label = None

    group_id_param = request.GET.get("group_id")
    teacher_id_param = request.GET.get("teacher_id")

    groups_data, _ = _safe_call(request, api.list_groups, token)

    lessons: List[Dict[str, Any]] = []
    error: Optional[str] = None
    current_source = ""

    if teacher_id_param and teacher_id_param.isdigit():
        teacher_id = int(teacher_id_param)
        lessons, error = _safe_call(request, api.lessons_by_teacher, token, teacher_id, week=week_filter)
        current_source = f"teacher:{teacher_id}"
    elif group_id_param and group_id_param.isdigit():
        group_id = int(group_id_param)
        lessons, error = _safe_call(request, api.lessons_by_group, token, group_id, week=week_filter)
        current_source = f"group:{group_id}"
    else:
        # Для студента — расписание его группы по умолчанию (если профиль студента есть)
        if user_role == "student":
            student_profile = user.get("student_profiles") or {}
            sgid = student_profile.get("group_id") if isinstance(student_profile, dict) else None
            if sgid:
                lessons, error = _safe_call(request, api.lessons_by_group, token, sgid, week=week_filter)
                current_source = f"group:{sgid}"
        # Для преподавателя — его собственное расписание
        elif user_role == "teacher":
            lessons, error = _safe_call(request, api.lessons_by_teacher, token, user.get("id"), week=week_filter)
            current_source = f"teacher:{user.get('id')}"

    lessons = lessons or []

    # Группируем занятия по дням недели и временным слотам для сетки
    # Бэкенд возвращает: id, group_id, teacher_id, teacher_name, day, week,
    #                    time_start, time_end, subject, lesson_type, room, building
    by_day: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    for lesson in lessons:
        day = lesson.get("day")
        if day in by_day:
            by_day[day].append(lesson)

    # Сортировка занятий в дне по времени
    for day in by_day:
        by_day[day].sort(key=lambda x: x.get("time_start", ""))

    days_data = [
        {"day": 1, "name": "Понедельник", "lessons": by_day[1]},
        {"day": 2, "name": "Вторник",     "lessons": by_day[2]},
        {"day": 3, "name": "Среда",       "lessons": by_day[3]},
        {"day": 4, "name": "Четверг",     "lessons": by_day[4]},
        {"day": 5, "name": "Пятница",     "lessons": by_day[5]},
        {"day": 6, "name": "Суббота",     "lessons": by_day[6]},
    ]

    return render(request, "pages/schedule.html", {
        "groups": groups_data or [],
        "days_data": days_data,
        "has_lessons": bool(lessons),
        "current_week": week_label,
        "current_source": current_source,
        "error": error,
    })


# ═══════════════════════════════════════════════════════════════
#  Посещаемость
# ═══════════════════════════════════════════════════════════════

@login_required_view
def attendance_page(request):
    token = _get_token(request)
    user = _get_user(request) or {}
    role = user.get("role")

    reports: List[Dict[str, Any]] = []
    error: Optional[str] = None

    if role == "student" and user.get("id"):
        reports, error = _safe_call(request, api.student_attendance, token, user["id"])
    elif role in {"teacher", "headman", "admin"}:
        # Преподаватель смотрит посещаемость по конкретному занятию
        lesson_id_param = request.GET.get("lesson_id")
        if lesson_id_param and lesson_id_param.isdigit():
            reports, error = _safe_call(request, api.lesson_attendance, token, int(lesson_id_param))
    reports = reports or []

    # Сводная статистика для KPI-карточек
    total = len(reports)
    present = sum(1 for r in reports if r.get("marked_via") in ("qr", "manual"))
    # На сервере нет статуса absent/excused — есть только факт отметки.
    # Поэтому в новой модели «отсутствовавших» считать с фронта нельзя,
    # без интеграции с расписанием. Покажем только посещённые.

    stats = {
        "present_count": present,
        "total_count": total,
        "missed_count": 0,  # информация ниже
        "excused_count": 0,
    }

    return render(request, "pages/attendance.html", {
        "reports": reports,
        "stats": stats,
        "user_role": role,
        "can_generate_qr": api.can_manage_attendance(role),
        "error": error,
    })


@login_required_view
def generate_qr_page(request, lesson_id: int):
    """Страница с QR-кодом для отметки на занятии (преподаватель)."""
    token = _get_token(request)
    user = _get_user(request) or {}
    if not api.can_manage_attendance(user.get("role")):
        return redirect("attendance")

    error: Optional[str] = None
    token_data: Optional[Dict[str, Any]] = None

    if request.method == "POST":
        token_data, error = _safe_call(request, api.create_attendance_token, token, lesson_id)

    return render(request, "pages/attendance_qr.html", {
        "lesson_id": lesson_id,
        "token_data": token_data,
        "qr_image_url": api.get_qr_image_url(lesson_id) if token_data else None,
        "error": error,
    })


# ═══════════════════════════════════════════════════════════════
#  Чаты
# ═══════════════════════════════════════════════════════════════

@login_required_view
@login_required_view
def chat_start_direct(request, user_id: int):
    """Открыть (или создать) личный чат с пользователем и перейти в него."""
    token = _get_token(request)
    me = _get_user(request) or {}
    if me.get("id") == user_id:
        return redirect("chats")
    chat, error = _safe_call(request, api.open_direct_chat, token, user_id)
    if error or not chat:
        # Если не удалось — вернёмся к списку чатов с сообщением
        chats, _ = _safe_call(request, api.list_chats, token)
        return render(request, "pages/chats.html", {
            "chats": chats or [],
            "error": error or "Не удалось открыть чат",
        })
    return redirect("chat_room", chat_id=chat["id"])


def chats_page(request):
    """Список чатов."""
    token = _get_token(request)
    chats, error = _safe_call(request, api.list_chats, token)
    return render(request, "pages/chats.html", {
        "chats": chats or [],
        "error": error,
    })


@login_required_view
def chat_room_page(request, chat_id: int):
    """Окно конкретного чата с WebSocket-клиентом."""
    token = _get_token(request)
    user = _get_user(request) or {}
    messages, error = _safe_call(request, api.chat_messages, token, chat_id, limit=100)

    # Карта id → имя участников (для отображения имён вместо «Пользователь #5»)
    names = {}
    chats, _ = _safe_call(request, api.list_chats, token)
    member_ids = []
    for c in chats or []:
        if c.get("id") == chat_id:
            member_ids = [m.get("user_id") for m in c.get("members", [])]
            break
    for uid in member_ids:
        if uid == user.get("id"):
            names[uid] = "Вы"
            continue
        u_data, _ = _safe_call(request, api.get_user, token, uid)
        if u_data:
            names[uid] = api.short_name(u_data) or f"Пользователь #{uid}"

    import json as _json
    return render(request, "pages/chat_room.html", {
        "chat_id": chat_id,
        "messages": messages or [],
        "user": user,
        "ws_url": api.get_chat_ws_url(chat_id, token),
        "names_json": _json.dumps(names, ensure_ascii=False),
        "error": error,
    })


# ═══════════════════════════════════════════════════════════════
#  Обработчик 404
# ═══════════════════════════════════════════════════════════════

def not_found_page(request, exception=None):
    return render(request, "pages/404.html", status=404)
