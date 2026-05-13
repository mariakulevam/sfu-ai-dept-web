# Dockerfile для веб-интерфейса кафедры СИИ ИКИТ СФУ
# Django в режиме production через Gunicorn

FROM python:3.12-slim

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Сначала зависимости (для эффективного кеширования слоёв Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка Gunicorn (production-сервер WSGI)
RUN pip install --no-cache-dir gunicorn

# Копируем код проекта
COPY . .

# Сборка статики (CSS, шрифты, лого)
RUN python manage.py collectstatic --noinput

# Открываем порт
EXPOSE 8000

# Запуск через Gunicorn — 3 воркера, тайм-аут 60 сек
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
