from django.contrib import admin

from AKOnline.models import VirtualRoom


@admin.register(VirtualRoom)
class VirtualRoomAdmin(admin.ModelAdmin):
    """
    Admin interface for virtual room model
    """
    model = VirtualRoom
    list_display = ['room', 'event', 'url']
    list_filter = ['room__event']

    def get_readonly_fields(self, request, obj=None):
        # Don't allow changing the room on existing virtual rooms
        # Instead, a link to the room editing form will be displayed automatically
        if obj:
            return self.readonly_fields + ('room', )
        return self.readonly_fields
