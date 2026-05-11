"""
Настройки Django-проекта сайта кафедры СИИ.
Бэкенд-сервис (FastAPI) указывается через переменные окружения / .env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем .env, если он есть рядом с manage.py
load_dotenv(BASE_DIR / ".env")


# ═══ Базовые настройки ═════════════════════════════════════════

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-CHANGE-ME-in-production-key-here-9382"
)
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")


# ═══ Приложения ════════════════════════════════════════════════

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ═══ Шаблоны ═══════════════════════════════════════════════════

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ═══ База данных (только для сессий — все данные приходят из FastAPI) ═══

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# ═══ Локализация ═══════════════════════════════════════════════

LANGUAGE_CODE = "ru-RU"
TIME_ZONE = "Asia/Krasnoyarsk"
USE_I18N = True
USE_TZ = True


# ═══ Статика ═══════════════════════════════════════════════════

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "core" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# ═══ Сессии ════════════════════════════════════════════════════

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 дней


# ═══ Интеграция с FastAPI-бэкендом команды ═════════════════════

FASTAPI_ROOT_URL = os.getenv("FASTAPI_ROOT_URL", "http://127.0.0.1:8001")
FASTAPI_API_BASE = f"{FASTAPI_ROOT_URL}/api/v1"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
