from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

# Django вызывает handler404 как (request, exception) — отдельная функция
handler404 = "core.views.not_found_page"
