from django.contrib import admin
from AKDashboard.models import DashboardButton


@admin.register(DashboardButton)
class DashboardButtonAdmin(admin.ModelAdmin):
    list_display = ['text', 'url', 'event']
    list_filter = ['event']
    search_fields = ['text', 'url']
    list_display_links = ['text']
