from django import forms
from django.contrib import admin

from AKPreference.models import AKPreference, EventParticipant
from AKModel.admin import PrepopulateWithNextActiveEventMixin
from AKModel.models import AK

@admin.register(EventParticipant)
class EventParticipantAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for EventParticipant
    """
    model = EventParticipant
    list_display = ['name', 'institution', 'event']
    list_filter = ['event', 'institution']
    list_editable = []
    ordering = ['name']


class AKPreferenceAdminForm(forms.ModelForm):
    """
    Adapted admin form for AK preferences for usage in :class:`AKPreferenceAdmin`)
    """
    class Meta:
        widgets = {
            'participant': forms.Select,
            'ak': forms.Select,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter possible values for foreign keys & m2m when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["participant"].queryset = EventParticipant.objects.filter(event=self.instance.event)
            self.fields["ak"].queryset = AK.objects.filter(event=self.instance.event)


@admin.register(AKPreference)
class AKPreferenceAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for AK preferences.
    Uses an adapted form (see :class:`AKPreferenceAdminForm`)
    """
    model = AKPreference
    form = AKPreferenceAdminForm
    list_display = ['preference', 'participant', 'ak', 'event']
    list_filter = ['event', 'ak', 'participant']
    list_editable = []
    ordering = ['participant', 'preference', 'ak']
