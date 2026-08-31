"""Root URL configuration.

Django checks these patterns top to bottom and uses the first match.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentication: register, login, refresh, profile.
    path("api/auth/", include("accounts.urls")),

    # Everything else under /api/ is handled by the tickets app's router.
    path("api/", include("tickets.urls")),

    # Gives the browsable API a login/logout link, so session auth works
    # while clicking around in development.
    path("api-auth/", include("rest_framework.urls")),
]
