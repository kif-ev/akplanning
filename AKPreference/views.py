from django import forms
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Exists, OuterRef
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, CreateView, TemplateView, UpdateView, DeleteView

from AKModel.metaviews import status_manager
from AKModel.metaviews.admin import EventSlugMixin, IntermediateAdminActionView
from AKModel.metaviews.status import TemplateStatusWidget
from AKModel.models import AKCategory
from AKPreference.models import AKPreference, EventParticipant
from .forms import EventParticipantForm, PreferenceForm, PreferenceFormSet


def uuid_key(event):
    """
    Determine the session key for the participant uuid for the given event
    :param event: event to determine the session key for
    :type event: Event
    :return: session key for the participant uuid for the given event
    :rtype: str
    """
    return f"preference_user_uuid_{event.slug}"


class PreferencePollCreateView(EventSlugMixin, SuccessMessageMixin, FormView):
    """
    View: Show a form to register the AK preference of a participant.

    The form creates the `EventParticipant` instance as well as the
    AKPreferences for each AK of the event.

    For the creation of the event participant, a `EventParticipantForm` is used.
    For the preferences, a ModelFormset is created.
    """


class EventSlugRedirectWhenInactiveMixin(EventSlugMixin):
    """
    Mixin to redirect to the dashboard when the event is not active
    """
    def dispatch(self, request, *args, **kwargs):
        self._load_event()
        if not self.event.active or (self.event.poll_hidden and not request.user.is_staff):
            messages.warning(request, _("Preference poll is not active"))
            return redirect(reverse_lazy("dashboard:dashboard_event", kwargs={"slug": self.event.slug}))
        return super().dispatch(request, *args, **kwargs)


class PreferencePollStartView(EventSlugRedirectWhenInactiveMixin, CreateView):
    """
    View: Start the preference poll for the event by showing the preference poll create form

    This view is used to start the preference poll for the event by showing the preference poll create form.
    """
    model = EventParticipant
    template_name = "AKPreference/poll_start.html"
    title = _("Start Preference Poll")
    form_class = EventParticipantForm

    def get_success_url(self):
        return reverse_lazy("poll:overview", kwargs={"event_slug": self.event.slug})

    def get(self, request, *args, **kwargs):
        # Check whether the user already registered for preference polling for this event and
        # redirect to second step in that case
        key = uuid_key(self.event)
        if key in request.session:
            if self.event.eventparticipant_set.filter(uuid=request.session[key]).exists():
                return redirect(self.get_success_url())
            # If the uuid in the session is not valid anymore (e.g. because the participant was deleted),
            # remove it from the session
            del request.session[uuid_key(self.event)]
            messages.warning(request,
                             _("There was an error discovering your previously entered information. "
                               "Please start again."))
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        s = super().form_valid(form)
        # Save the uuid of the created participant in the session to recognize the user in the next step
        self.request.session[uuid_key(self.event)] = str(self.object.uuid)
        return s

    def get_initial(self):
        # Load initial values for the form
        # Used to directly add the first owner and the event this AK will belong to
        initials = super().get_initial()
        initials['event'] = self.event
        return initials


class CheckSessionForParticipantMixin:
    """
    Mixin to check whether the session contains a valid participant uuid for the event and redirect to the start page if not
    """
    def get(self, request, *args, **kwargs):
        # Check whether the user already registered for preference polling for this event and
        # redirect to second step in that case
        key = uuid_key(self.event)
        if not key in request.session:
            return redirect(reverse_lazy("poll:start", kwargs={"event_slug": self.event.slug}))
        if not self.event.eventparticipant_set.filter(uuid=request.session[key]).exists():
            # If the uuid in the session is not valid anymore (e.g. because the participant was deleted),
            # remove it from the session
            del request.session[uuid_key(self.event)]
            messages.warning(request,
                             _("There was an error discovering your previously entered information. "
                               "Please start again."))
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy("poll:overview", kwargs={"event_slug": self.event.slug})


class PreferencePollOverview(EventSlugRedirectWhenInactiveMixin, CheckSessionForParticipantMixin, TemplateView):
    """
    View: Show an overview of the preference poll for the event

    This view is used to show an overview of the preference poll for the event, including the number of participants
    and preferences registered so far.
    """
    template_name = "AKPreference/poll_overview.html"
    title = _("Preference Poll Overview")

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['uuid'] = self.request.session.get(uuid_key(self.event), None)
        context['participant'] = self.event.eventparticipant_set.get(uuid=context['uuid'])
        context['categories'] = self.event.akcategory_set.all().annotate(
            has_saved_preferences=Exists(
                AKPreference.objects.filter(
                    ak__category=OuterRef('pk'),
                    participant=context['participant']
                )
            )
        )
        return context


class ParticipantUpdateView(EventSlugRedirectWhenInactiveMixin, CheckSessionForParticipantMixin, UpdateView):
    """
    View: Update the participant information for the preference poll
    """
    model = EventParticipant
    template_name = "AKPreference/poll_start.html"
    title = _("Update information")
    form_class = EventParticipantForm

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _("Information updated."))
        return r

    def get_object(self, queryset=...):
        return EventParticipant.objects.get(uuid=self.request.session[uuid_key(self.event)])


class DeleteInformationAndPreferencesView(EventSlugRedirectWhenInactiveMixin, CheckSessionForParticipantMixin, DeleteView):
    """
    View: Delete the participant information and preferences for the preference poll
    """
    model = EventParticipant
    template_name = "AKPreference/poll_delete.html"
    title = _("Delete information and preferences")

    def get_success_url(self):
        # After deleting the participant, also remove the uuid from the session to allow re-entering the poll
        key = uuid_key(self.event)
        if key in self.request.session:
            del self.request.session[key]
        return reverse_lazy("dashboard:dashboard_event", kwargs={"slug": self.event.slug})

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _("Your information and preferences were deleted."))
        return super().delete(request, *args, **kwargs)

    def get_object(self, queryset=...):
        return EventParticipant.objects.get(uuid=self.request.session[uuid_key(self.event)])


class EnterPreferencesView(EventSlugRedirectWhenInactiveMixin, CheckSessionForParticipantMixin, FormView):
    template_name = 'AKPreference/poll_preferences.html'
    model = EventParticipant

    def dispatch(self, request, *args, **kwargs):
        self.ak_category = get_object_or_404(AKCategory, pk=self.kwargs['category_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['participant'] = self.get_object()
        kwargs['category'] = self.ak_category
        return kwargs

    def get_form_class(self):
        existing_preferences_ak_ids = self.get_object().akpreference_set.values_list('ak', flat=True)
        aks_without_preferences = self.ak_category.ak_set.exclude(pk__in=existing_preferences_ak_ids).prefetch_related('owners')
        self.initial = [
            {
                'event': self.event,
                'participant': self.get_object(),
                'ak': ak,
            } for ak in aks_without_preferences
        ]

        return forms.modelformset_factory(AKPreference, form=PreferenceForm, formset=PreferenceFormSet,
                                          extra=len(self.initial))

    def get_object(self, queryset=...):
        if not hasattr(self, "object") or self.object is None:
            self.object = EventParticipant.objects.get(uuid=self.request.session[uuid_key(self.event)])
        return self.object

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['category'] = self.ak_category
        ak_details = {ak.pk: ak for ak in self.ak_category.ak_set.prefetch_related('owners').all()}
        for f in context['form']:
            # If type of initial['ak'] is not string
            ak = ak_details[f.initial['ak']] if isinstance(f.initial['ak'], int) else f.initial['ak']
            f.fields["preference"].label = ak.name
            f.fields["preference"].help_text = (
                    _("Description: ") + ak.description
            )
            f.ak_obj = ak
        return context

    def form_valid(self, form):
        count_saved = 0
        count_deleted = 0

        # Loop over all forms in the formset and store all preferences that are not "ignore"
        # Delete previously saved preferences that are now set to "ignore"
        for f in form.forms:
            if "preference" in f.cleaned_data:
                o = f.save(commit=False)
                if f.cleaned_data['preference'] > 0:
                    o.save()
                    count_saved += 1
                else:
                    o.delete()
                    count_deleted += 1

        messages.success(
            self.request,
            _(f"{count_saved} Preferences saved/updated, {count_deleted} previously saved Preferences deleted.")
        )
        return redirect(self.get_success_url())


@status_manager.register(name="preferences")
class PreferenceOverviewWidget(TemplateStatusWidget):
    """
    Status page widget: Preferences
    """
    required_context_type = "event"
    title = _("Preference Poll Summary")
    template_name = "admin/AKPreference/status/preference_overview.html"

    def get_context_data(self, context) -> dict:
        context = super().get_context_data(context)
        context["participants_count"] = context["event"].eventparticipant_set.count()
        context["preference_count"] = context["event"].akpreference_set.count()
        return context


class AnonymizeParticipantsView(IntermediateAdminActionView):
    """
    View: Confirmation page to anonymize all given participants by removing their name and institution

    Confirmation functionality provided by :class:`AKModel.metaviews.admin.IntermediateAdminView`
    """
    title = _("Anonymize participants")
    model = EventParticipant
    confirmation_message = _("The following participants will be anonymized by removing their name and institution. "
                             "This cannot be undone!")
    success_message = _("Participants successfully anonymized.")

    def action(self, form):
        self.entities.update(name='', institution='')
