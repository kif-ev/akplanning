from django import forms
from django.contrib import admin
from django.contrib.admin import action
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import path, reverse_lazy

from AKPreference.models import AKPreference, EventParticipant
from AKPreference.views import AnonymizeParticipantsView, ParticipantAdminView
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
    actions = ['anonymize']
    form = EventParticipantAdminForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(preference_count=Count('akpreference'))

    def preference_count(self, obj):
        """
        Access the annotated preference count for the participants as field in the admin list view
        :param obj: partipipant object
        :return: annotated preference count
        """
        return format_html("<a href='{url}'>{text}</a>",
                url=reverse_lazy('admin:participant-details', kwargs={'pk': obj.pk}),
                text=obj.preference_count)
    preference_count.admin_order_field = 'preference_count'
    preference_count.short_description = _('Count of saved preferences')

    def get_urls(self):
        """
        Add additional URLs/views
        Currently used to reset the interest field and interest counter field
        """
        urls = [
            path('anonymize-participants/', self.admin_site.admin_view(AnonymizeParticipantsView.as_view()),
                 name="preference-anonymize-participants"),
            path('details/<pk>/', self.admin_site.admin_view(ParticipantAdminView.as_view()),
                 name="participant-details"),
        ]
        urls.extend(super().get_urls())
        return urls

    @action(description=_("Anonymize participants"))
    def anonymize(self, request, queryset):
        """
        Action: Anonymize selected participants
        Will use a typical admin confirmation view flow
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
                f"{reverse_lazy('admin:preference-anonymize-participants')}?pks={','.join(str(pk) for pk in selected)}")


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
    list_filter = ['event',
                   ('ak', EventRelatedFieldListFilter),
                   ('participant', EventRelatedFieldListFilter),
                   'preference']
    list_editable = []
    ordering = ['participant', 'preference', 'ak']
