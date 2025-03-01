from django import forms
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView

from AKModel.metaviews.admin import EventSlugMixin
from AKModel.models import AK, AKPreference

from .forms import EventParticipantForm


class PreferencePollCreateView(EventSlugMixin, SuccessMessageMixin, CreateView):
    """
    View: Show a form to register the AK preference of a participant.

    The form creates the `EventParticipant` instance as well as the
    AKPreferences for each AK of the event.

    For the creation of the event participant, a `EventParticipantForm` is used.
    For the preferences, a ModelFormset is created.
    """

    model = AKPreference
    form_class = forms.modelform_factory(
        model=AKPreference, fields=["preference", "slot", "event"]
    )
    template_name = "AKPreferencePoll/poll.html"
    success_message = "Preferences of %(name)s were registered successfully"

    def _create_modelformset(self):
        return forms.modelformset_factory(
            model=AKPreference,
            fields=["preference", "slot", "event"],
            widgets={
                "slot": forms.HiddenInput,
                "event": forms.HiddenInput,
                "preference": forms.RadioSelect,
            },
            extra=0,
        )

    def get_success_url(self):
        return reverse_lazy(
            "dashboard:dashboard_event", kwargs={"slug": self.event.slug}
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ak_set = (
            AK.objects.filter(event=self.event)
            .prefetch_related("akslot_set")
            .order_by()
            .all()
        )
        initial_lst = [
            {"slot": ak.akslot_set.first(), "event": self.event} for ak in ak_set
        ]

        context["formset"] = self._create_modelformset()(
            queryset=AKPreference.objects.none(),
            initial=initial_lst,
        )
        context["formset"].extra = len(initial_lst)

        for form, init in zip(context["formset"], initial_lst, strict=True):
            form.fields["preference"].label = init["slot"].ak.name
            form.fields["preference"].help_text = (
                "Description: " + init["slot"].ak.description
            )

        context["participant_form"] = EventParticipantForm(
            initial={"event": self.event}
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
        formset, participant_form = form
        participant = participant_form.save()
        instances = formset.save(commit=False)
        for instance in instances:
            instance.participant = participant
            instance.save()
        success_message = self.get_success_message(participant_form.cleaned_data)
        if success_message:
            messages.success(self.request, success_message)
        return HttpResponseRedirect(self.get_success_url())
