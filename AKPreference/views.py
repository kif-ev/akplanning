import json
from itertools import groupby

from django import forms
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Exists, OuterRef
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, CreateView, TemplateView, UpdateView, DeleteView

from AKModel.availability.models import Availability
from AKModel.availability.serializers import AvailabilityFormSerializer
from AKModel.metaviews import status_manager
from AKModel.metaviews.admin import EventSlugMixin, IntermediateAdminActionView
from AKModel.metaviews.status import TemplateStatusWidget
from AKModel.models import AK
from AKPreference.models import AKPreference, EventParticipant
from .forms import EventParticipantForm


class PreferencePollCreateView(EventSlugMixin, SuccessMessageMixin, FormView):
    """
    View: Show a form to register the AK preference of a participant.

    The form creates the `EventParticipant` instance as well as the
    AKPreferences for each AK of the event.

    For the creation of the event participant, a `EventParticipantForm` is used.
    For the preferences, a ModelFormset is created.
    """

    form_class = forms.Form
    model = AKPreference
    form_class = forms.modelform_factory(
            model=AKPreference, fields=["preference", "ak", "event"]
    )
    template_name = "AKPreference/poll.html"
    success_message = _("AK preferences were registered successfully")

    def _create_modelformset(self):
        return forms.modelformset_factory(
                model=AKPreference,
                fields=["preference", "ak", "event"],
                widgets={
                    "ak": forms.HiddenInput,
                    "event": forms.HiddenInput,
                    "preference": forms.RadioSelect,
                },
                extra=0,
        )

    def get(self, request, *args, **kwargs):
        s = super().get(request, *args, **kwargs)
        # Don't show preference form when event is not active or poll is hidden -> redirect to dashboard
        if not self.event.active or (self.event.poll_hidden and not request.user.is_staff):
            return redirect(self.get_success_url())
        return s

    def get_success_url(self):
        return reverse_lazy(
                "dashboard:dashboard_event", kwargs={"slug": self.event.slug}
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ak_set = (
            AK.objects.filter(event=self.event)
            .order_by()
            .all()
            .prefetch_related('owners')
        )
        initial_lst = [
            {"ak": ak, "event": self.event} for ak in ak_set
        ]

        context["formset"] = self._create_modelformset()(
                queryset=AKPreference.objects.none(),
                initial=initial_lst,
        )
        context["formset"].extra = len(initial_lst)

        for form, init in zip(context["formset"], initial_lst, strict=True):
            form.fields["preference"].label = init["ak"].name
            form.fields["preference"].help_text = (
                    "Description: " + init["ak"].description
            )
            form.ak_obj = init["ak"]

        sorted_forms = sorted(
                context["formset"],
                key=lambda f: (f.ak_obj.category.name, f.ak_obj.id)
        )
        grouped_forms = [
            (category, list(forms))
            for category, forms in groupby(sorted_forms, key=lambda f: f.ak_obj.category)
        ]
        context["grouped_forms"] = grouped_forms
        availabilities_serialization = AvailabilityFormSerializer(
                (
                    [Availability.with_event_length(event=self.event)],
                    self.event,
                )
        )

        context["participant_form"] = EventParticipantForm(
                initial={
                    "event": self.event,
                    "availabilities": json.dumps(availabilities_serialization.data),
                }
        )
        context['show_types'] = self.event.aktype_set.count() > 0
        return context

    def post(self, request, *args, **kwargs):
        self._load_event()
        model_formset_cls = self._create_modelformset()
        formset = model_formset_cls(request.POST)
        participant_form = EventParticipantForm(
                data=request.POST, initial={"event": self.event}
        )
        if formset.is_valid() and participant_form.is_valid():
            return self.form_valid(form=(formset, participant_form))
        return self.form_invalid(form=(formset, participant_form))

    def form_valid(self, form):
        try:
            formset, participant_form = form
            participant = participant_form.save()
            instances = formset.save(commit=False)
            for instance in instances:
                instance.participant = participant
                instance.save()
            success_message = self.get_success_message(participant_form.cleaned_data)
            if success_message:
                messages.success(self.request, success_message)
        except:
            messages.error(
                    self.request,
                    _(
                            "Something went wrong. Your preferences were not saved. "
                            "Please try again or contact the organizers."
                    ),
            )
            return self.form_invalid(form=form)
        return redirect(self.get_success_url())


class EventSlugRedirectWhenInactiveMixin(EventSlugMixin):
    """
    Mixin to redirect to the dashboard when the event is not active
    """
    def dispatch(self, request, *args, **kwargs):
        self._load_event()
        if not self.event.active or (self.event.poll_hidden and not request.user.is_staff):
            messages.warning(request, _("Preference poll is not active"))
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)


class PreferencePollStartView(EventSlugMixin, CreateView):
    """
    View: Start the preference poll for the event by showing the preference poll create form

    This view is used to start the preference poll for the event by showing the preference poll create form.
    """
    model = EventParticipant
    template_name = "AKPreference/poll_start.html"
    title = _("Start Preference Poll")
    form_class = EventParticipantForm

    def get_success_url(self):
        return reverse_lazy("poll:poll-overview", kwargs={"event_slug": self.event.slug})

    def get(self, request, *args, **kwargs):
        # Check whether the user already registered for preference polling for this event and
        # redirect to second step in that case
        if "preference_user_uuid" in request.session:
            if self.event.eventparticipant_set.filter(uuid=request.session["preference_user_uuid"]).exists():
                return redirect(self.get_success_url())
            # If the uuid in the session is not valid anymore (e.g. because the participant was deleted),
            # remove it from the session
            del request.session["preference_user_uuid"]
            messages.warning(request,
                             _("There was an error discovering your previously entered information. "
                               "Please start again."))
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        s = super().form_valid(form)
        # Save the uuid of the created participant in the session to recognize the user in the next step
        self.request.session["preference_user_uuid"] = str(self.object.uuid)
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
        if not "preference_user_uuid" in request.session:
            return redirect(reverse_lazy("poll:poll-start", kwargs={"event_slug": self.event.slug}))
        elif not self.event.eventparticipant_set.filter(uuid=request.session["preference_user_uuid"]).exists():
            # If the uuid in the session is not valid anymore (e.g. because the participant was deleted),
            # remove it from the session
            del request.session["preference_user_uuid"]
            messages.warning(request,
                             _("There was an error discovering your previously entered information. "
                               "Please start again."))
        return super().get(request, *args, **kwargs)


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
        context['uuid'] = self.request.session.get("preference_user_uuid", None)
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

    def get_success_url(self):
        return reverse_lazy("poll:poll-overview", kwargs={"event_slug": self.event.slug})

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _("Information updated."))
        return r

    def get_object(self, queryset=...):
        return EventParticipant.objects.get(uuid=self.request.session['preference_user_uuid'])


class DeleteInformationAndPreferencesView(EventSlugRedirectWhenInactiveMixin, CheckSessionForParticipantMixin, DeleteView):
    """
    View: Delete the participant information and preferences for the preference poll
    """
    model = EventParticipant
    template_name = "AKPreference/poll_delete.html"
    title = _("Delete information and preferences")

    def get_success_url(self):
        # After deleting the participant, also remove the uuid from the session to allow re-entering the poll
        if "preference_user_uuid" in self.request.session:
            del self.request.session["preference_user_uuid"]
        return reverse_lazy("dashboard:dashboard_event", kwargs={"slug": self.event.slug})

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _("Your information and preferences were deleted."))
        return super().delete(request, *args, **kwargs)

    def get_object(self, queryset=...):
        return EventParticipant.objects.get(uuid=self.request.session['preference_user_uuid'])


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
