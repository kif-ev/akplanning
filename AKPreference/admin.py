from django import forms
from django.contrib import admin
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from AKPreference.models import AKPreference, EventParticipant
from AKModel.admin import PrepopulateWithNextActiveEventMixin, EventRelatedFieldListFilter
from AKModel.models import AK, AKRequirement


class EventParticipantAdminForm(forms.ModelForm):
    """
    Adapted admin form for EventParticipant for usage in :class:`EventParticipantAdmin`)
    """
    class Meta:
        widgets = {
            "requirements": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter possible values for foreign keys & m2m when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["requirements"].queryset = AKRequirement.objects.filter(event=self.instance.event)


@admin.register(EventParticipant)
class EventParticipantAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for EventParticipant
    """
    model = EventParticipant
    list_display = ['name', 'institution', 'event', 'uuid', 'preference_count']
    list_filter = ['event', 'institution']
    list_editable = []
    readonly_fields = ['uuid']
    ordering = ['name']
    form = EventParticipantAdminForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(preference_count=Count('akpreference'))

    def preference_count(self, obj):
        return obj.preference_count
    preference_count.admin_order_field = 'preference_count'
    preference_count.short_description = _('Count of saved preferences')


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
    list_filter = ['event', ('ak', EventRelatedFieldListFilter), ('participant', EventRelatedFieldListFilter)]
    list_editable = []
    ordering = ['participant', 'preference', 'ak']
