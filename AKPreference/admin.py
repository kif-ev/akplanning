from django import forms
from django.contrib import admin
from django.contrib.admin import action
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.urls import path, reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from AKModel.admin_utils import EventRelatedFieldListFilter, PrepopulateWithNextActiveEventMixin
from AKModel.forms import EventRestrictedFieldsFormMixin
from AKPreference.models import AKPreference, EventParticipant
from AKPreference.views import AnonymizeParticipantsView, ParticipantAdminView


class EventParticipantAdminForm(EventRestrictedFieldsFormMixin, forms.ModelForm):
    """
    Adapted admin form for EventParticipant for usage in :class:`EventParticipantAdmin`)
    """
    class Meta:
        event_restricted_fields = ["requirements", "ak_owner"]
        widgets = {
            "requirements": forms.CheckboxSelectMultiple,
        }


@admin.register(EventParticipant)
class EventParticipantAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for EventParticipant
    """
    model = EventParticipant
    list_display = ['name', 'institution', 'event', 'ak_owner', 'uuid', 'preference_count']
    list_select_related = ['event', 'ak_owner']
    list_filter = ['event', 'institution']
    list_editable = []
    readonly_fields = ['uuid']
    ordering = ['name']
    actions = ['anonymize']
    form = EventParticipantAdminForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Preferences for AKs owned by the participant are ignored (see AKPreference.for_owned_ak)
        counted_preferences = (AKPreference.objects.filter(participant=OuterRef('pk'))
                               .exclude(AKPreference.for_owned_ak())
                               .order_by().values('participant').annotate(count=Count('pk')).values('count'))
        return qs.annotate(preference_count=Coalesce(Subquery(counted_preferences), 0))

    @admin.display(description=_('Count of saved preferences'), ordering='preference_count')
    def preference_count(self, obj):
        """
        Access the annotated preference count for the participants as field in the admin list view
        :param obj: partipipant object
        :return: annotated preference count
        """
        return format_html("<a href='{url}'>{text}</a>",
                           url=reverse_lazy('admin:participant-details', kwargs={'pk': obj.pk}),
                           text=obj.preference_count)

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


class AKPreferenceAdminForm(EventRestrictedFieldsFormMixin, forms.ModelForm):
    """
    Adapted admin form for AK preferences for usage in :class:`AKPreferenceAdmin`)
    """
    class Meta:
        event_restricted_fields = ["participant", "ak"]
        widgets = {
            'participant': forms.Select,
            'ak': forms.Select,
        }


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
