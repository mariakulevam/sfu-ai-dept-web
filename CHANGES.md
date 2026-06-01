# Изменения фронта под новый бэк Риты

## Кратко
Серверная часть переехала с одной версии на другую: убран `GET /auth/me`
и `GET /users/{id}`, добавлен модуль ВКР, новая роль `deputy_head`, регистрация
теперь требует `group_id`, появились `PATCH /users/me/*-profile`, сброс пароля
через email. Этот пакет правок подгоняет под это веб-фронт.

## Что изменено в этой итерации

### 1. `core/services/api_client.py`
- **`get_user(token, user_id)`** переписан. Раньше дёргал `GET /users/{id}`
  (этого эндпоинта в новом бэке нет). Теперь:
  - сначала идёт в `GET /users` (видимые пользователю);
  - если там нет — в публичный `GET /users/teachers`;
  - результаты кэшируются на 60 секунд по токену (in-memory),
    чтобы не дёргать API на каждый рендер списка чатов.
  - возвращает `None`, если пользователя не нашли (фронт показывает заглушку).

### 2. `core/urls.py`
Добавлены маршруты:
```
/vkr/                          → vkr_topics
/vkr/my/                       → vkr_my_topics
/vkr/new/                      → vkr_propose
/vkr/<int:topic_id>/           → vkr_topic_detail
/vkr/<int:topic_id>/review/    → vkr_topic_review
/reset-password/               → reset_password
```

### 3. Новые шаблоны
- `core/templates/pages/vkr_topics.html` — лента всех тем (с фильтром
  по статусу для замзав/админа, без — для остальных).
- `core/templates/pages/vkr_my_topics.html` — мои предложенные темы.
- `core/templates/pages/vkr_topic_detail.html` — карточка темы +
  форма одобрения/отклонения (только замзав).
- `core/templates/pages/vkr_propose.html` — форма «предложить тему».
- `core/templates/pages/reset_password.html` — сброс пароля по email.
- `core/templates/pages/403.html` — страница «Доступ запрещён»
  (на неё перенаправляют отказы в правах).

### 4. Обновлённые шаблоны
- `register.html` — добавлено поле «Учебная группа». Если список групп
  загрузился — выпадающий `<select>`, если нет — числовое поле с подсказкой.
  Без этого регистрация студента валится с 422 — бэк теперь требует `group_id`.
- `login.html` — добавлена ссылка «Забыли пароль?» под полем пароля.
- `profile.html` — новая карточка «Контактные данные» с разными
  полями в зависимости от роли:
  - студент/староста: phone, telegram, vk;
  - преподаватель/замзав: department, positions (мультивыбор), phone, cabinet;
  - декан: faculty, position, phone, cabinet.
- `includes/header.html` — пункт «Темы ВКР» в десктопной шапке.
- `includes/sidebar.html` — пункт «Темы ВКР» в мобильной боковой панели,
  раздел «Учебная работа».

### 5. `core/views.py`
- В `profile_page` добавлен обработчик `action == "update_contacts"`,
  который по роли пользователя вызывает `update_student_profile` /
  `update_teacher_profile` / `update_dean_profile`.
- В контекст profile прокидывается `teacher_position_options` — список
  пар (код, человекочитаемая метка) для чекбоксов должностей.

## Что уже было в проекте (Маша/предыдущая итерация)
Эти вещи уже были подогнаны до моих правок:
- `get_current_user` использует `/users/me`.
- `register_user` принимает `group_id`.
- `reset_password(email)` обращается к `/auth/reset-password`.
- VKR-функции в api_client: `propose_vkr_topic`, `list_my_vkr_topics`,
  `list_approved_vkr_topics`, `list_all_vkr_topics`, `get_vkr_topic`,
  `review_vkr_topic`, `bulk_delete_vkr_topics`.
- Утилиты `can_propose_vkr_topic`, `can_review_vkr_topics`,
  `can_view_all_vkr_topics`, `can_view_approved_vkr_topics`.
- View-функции для ВКР и сброса пароля.
- Передача `groups` в шаблон регистрации.

## Что не делал (опционально, на будущее)
- В `manage_staff.html` кнопка «Назначить группу» для декана
  (`PATCH /users/{id}/group`) — backend готов, фронт пока не вызывает.
- На странице события подгрузка изображения через `GET /events/{id}/image`
  вместо прямого `media`-URL.
- Адаптация `chat.send_message` для отправки сообщений через REST
  (`POST /chats/{id}/messages`) как фолбэк, если WebSocket недоступен.
- Страница со списком одобренных тем ВКР для распределения студентам.

## Развёртывание
```bash
docker compose down
git pull              # или замени файлы вручную
docker compose build web
docker compose up -d
```
Если БД бэка ещё не накатила новые миграции — нужно сначала запустить
`alembic upgrade head` со стороны Ритиной части.
