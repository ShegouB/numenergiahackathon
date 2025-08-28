# numenergia_project/urls.py

from django.contrib import admin
from django.urls import path, include # N'oubliez pas d'importer 'include'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('core.urls')), # Inclure les URLs de l'application 'core'
]
