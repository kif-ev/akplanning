from django.contrib import admin

from AKDashboard.models import DashboardButton, EventFact


@admin.register(DashboardButton)
class DashboardButtonAdmin(admin.ModelAdmin):
    """
    Admin interface for dashboard buttons
    """
    list_display = ['text', 'url', 'event']
    list_filter = ['event']
    search_fields = ['text', 'url']
    list_display_links = ['text']


@admin.register(EventFact)
class EventFactAdmin(admin.ModelAdmin):
    """
    Admin interface for manually maintained event facts
    """
    list_display = ['title', 'value', 'order', 'event']
    list_filter = ['event']
    search_fields = ['title', 'value']
    list_display_links = ['title']
