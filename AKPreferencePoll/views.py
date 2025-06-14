import json

from django import forms
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from AKModel.availability.models import Availability
from AKModel.availability.serializers import AvailabilityFormSerializer
from AKModel.metaviews.admin import EventSlugMixin
from AKModel.models import AK, AKPreference

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
    template_name = "AKPreferencePoll/poll.html"
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
