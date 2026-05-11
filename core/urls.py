from django.urls import path

from . import views

urlpatterns = [
    # Публичные
    path("", views.home_page, name="home"),
    path("about/", views.about_page, name="about"),
    path("staff/", views.staff_page, name="staff"),

    # Авторизация
    path("login/", views.login_page, name="login"),
    path("logout/", views.logout_page, name="logout"),
    path("profile/", views.profile_page, name="profile"),

    # Объявления
    path("announcements/", views.announcements_page, name="announcements"),
    path("announcements/<int:announcement_id>/", views.announcement_detail_page,
         name="announcement_detail"),
    path("announcements/new/", views.announcements_page, name="announcement_new"),

    # Прочие модули
    path("events/", views.events_page, name="events"),
    path("documents/", views.documents_page, name="documents"),
    path("schedule/", views.schedule_page, name="schedule"),
    path("attendance/", views.attendance_page, name="attendance"),
]
