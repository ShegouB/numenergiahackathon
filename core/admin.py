# core/admin.py

from django.contrib import admin
from .models import FinancialAssumptions, SolarPanel, WaterPump, Battery

admin.site.register(FinancialAssumptions)
admin.site.register(SolarPanel)
admin.site.register(WaterPump)
admin.site.register(Battery)
