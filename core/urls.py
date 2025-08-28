# core/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('signup/', views.SignUpView.as_view(), name='signup'), 
    path('api/calculate', views.calculate_api, name='calculate_api'),
    path('api/generate-report', views.generate_pdf_report, name='generate_report'),
    path('api/history', views.history_api, name='history_api'),
    path('api/hourly-production', views.hourly_production_api, name='hourly_production_api'), 
]
