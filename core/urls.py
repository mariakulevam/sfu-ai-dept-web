from django.urls import path
from . import views

urlpatterns = [
    # Публичные
    path("", views.home_page, name="home"),
    path("about/", views.about_page, name="about"),
    path("programs/", views.programs_page, name="programs"),
    path("staff/", views.staff_page, name="staff"),
    path("staff/manage/", views.manage_staff_page, name="manage_staff"),

    # Авторизация
    path("login/", views.login_page, name="login"),
    path("logout/", views.logout_page, name="logout"),
    path("register/", views.register_page, name="register"),
    path("profile/", views.profile_page, name="profile"),

    # Объявления
    path("announcements/", views.announcements_page, name="announcements"),
    path("announcements/new/", views.announcement_create_page, name="announcement_new"),
    path("announcements/<int:announcement_id>/", views.announcement_detail_page, name="announcement_detail"),
    path("announcements/<int:announcement_id>/edit/", views.announcement_edit_page, name="announcement_edit"),
    path("announcements/<int:announcement_id>/archive/", views.announcement_archive, name="announcement_archive"),
    path("announcements/<int:announcement_id>/restore/", views.announcement_restore, name="announcement_restore"),
    path("announcements/<int:announcement_id>/delete/", views.announcement_delete, name="announcement_delete"),

    # События
    path("events/", views.events_page, name="events"),
    path("events/new/", views.event_create_page, name="event_new"),
    path("events/<int:event_id>/edit/", views.event_edit_page, name="event_edit"),
    path("events/<int:event_id>/delete/", views.event_delete, name="event_delete"),

    # Документы и расписание
    path("documents/", views.documents_page, name="documents"),
    path("documents/<int:doc_id>/download/", views.document_download, name="document_download"),
    path("schedule/", views.schedule_page, name="schedule"),

    # Посещаемость и QR
    path("attendance/", views.attendance_page, name="attendance"),
    path("attendance/qr/<int:lesson_id>/", views.generate_qr_page, name="attendance_qr"),

    # Чат
    path("chats/", views.chats_page, name="chats"),
    path("chats/new/", views.chat_new_page, name="chat_new"),
    path("chats/start/<int:user_id>/", views.chat_start_direct, name="chat_start_direct"),
    path("chats/<int:chat_id>/", views.chat_room_page, name="chat_room"),
]
