"""
Reusable building blocks for model admins of event-related models
(list filters and mixins for :class:`django.contrib.admin.ModelAdmin` subclasses)
"""
from django.contrib.admin import RelatedFieldListFilter
from django.utils import timezone

from AKModel.models import Event
from AKModel.typing_utils import ModelAdminMixinBase


class EventRelatedFieldListFilter(RelatedFieldListFilter):
    """
    Reusable filter to restrict the possible choices of a field to those belonging to a certain event
    as specified in the event__id__exact GET parameter.
    The choices are only restricted if this parameter is present, otherwise all choices are used/returned
    """

    def field_choices(self, field, request, model_admin):
        ordering = self.field_admin_ordering(field, request, model_admin)
        limit_choices = {}
        if "event__id__exact" in request.GET:
            limit_choices['event__id__exact'] = request.GET["event__id__exact"]
        return field.get_choices(include_blank=False, limit_choices_to=limit_choices, ordering=ordering)


class PrepopulateWithNextActiveEventMixin(ModelAdminMixinBase):
    """
    Mixin for automated pre-population of the event field
    """

    # pylint: disable=too-few-public-methods

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Override field generation for foreign key fields to introduce special handling for event fields:
        Pre-populate the event field with the next active event (since that is the most likeliest event to be worked
        on in the admin interface) to make creation of new owners easier
        """
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class EventTimezoneFormMixin(ModelAdminMixinBase):
    """
    Mixin to enforce the usage of the timezone of the associated event in forms
    """

    # pylint: disable=too-few-public-methods

    def get_form(self, request, obj=None, change=False, **kwargs):
        """
        Override form creation, use timezone of associated event
        """
        if obj is not None and obj.event.timezone:
            timezone.activate(obj.event.timezone)
        # No timezone available? Use UTC
        else:
            timezone.activate("UTC")
        return super().get_form(request, obj, change, **kwargs)
