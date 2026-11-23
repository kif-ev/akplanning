from django.apps import apps
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, FormView, UpdateView

from AKModel.forms import NewEventWizardActivateForm, NewEventWizardImportForm, NewEventWizardPrepareImportForm, \
    NewEventWizardSettingsForm, NewEventWizardStartForm
from AKModel.metaviews.admin import AdminViewMixin, EventSlugMixin, WizardViewMixin
from AKModel.models import Event, StatusTrackingEntry
from AKModel.status_tracking import status_tracker

Progress = StatusTrackingEntry.Progress


class NewEventWizardMixin(WizardViewMixin):
    """
    Mixin for all views of the new event wizard (defines title and steps of the wizard)
    """
    # pylint: disable=too-few-public-methods
    wizard_title = _("New event wizard")
    wizard_steps = [
        _("Start"),
        _("Settings"),
        _("Event created, Prepare Import"),
        _("Import categories & requirements"),
        _("Activate?"),
        _("Finish")
    ]


class NewEventWizardStartView(AdminViewMixin, NewEventWizardMixin, CreateView):
    """
    Wizard view: Entry/Start

    Specify basic settings, especially the timezone for correct time treatment in the next view
    (:class:`NewEventWizardSettingsView`) where this view will redirect to without saving the new event already
    """
    model = Event
    form_class = NewEventWizardStartForm
    template_name = "admin/AKModel/event_wizard/start.html"
    wizard_step = 1


class NewEventWizardSettingsView(AdminViewMixin, NewEventWizardMixin, CreateView):
    """
    Wizard view: Event settings

    Specify most of the event settings. The user will see that certain fields are required since they were lead here
    from another form in :class:`NewEventWizardStartView` that did not contain these fields even though they are
    mandatory for the event model

    Next step will then be :class:`NewEventWizardPrepareImportView` to prepare copy configuration elements
    from an existing event
    """
    model = Event
    form_class = NewEventWizardSettingsForm
    template_name = "admin/AKModel/event_wizard/settings.html"
    wizard_step = 2

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["timezone"] = context["form"].cleaned_data["timezone"]
        return context

    def get_success_url(self):
        return reverse_lazy("admin:new_event_wizard_prepare_import", kwargs={"event_slug": self.object.slug})


class NewEventWizardPrepareImportView(NewEventWizardMixin, EventSlugMixin, FormView):
    """
    Wizard view: Choose event to copy configuration elements from

    The user can here select an existing event to copy elements like requirements, categories and dashboard buttons from
    The exact subset of elements to copy from can then be selected in the next view (:class:`NewEventWizardImportView`)

    Instead, this step can be skipped by directly continuing with :class:`NewEventWizardActivateView`
    """
    form_class = NewEventWizardPrepareImportForm
    template_name = "admin/AKModel/event_wizard/created_prepare_import.html"
    wizard_step = 3

    def form_valid(self, form):
        # Selected a valid event to import from? Use this to go to next step of wizard
        return redirect("admin:new_event_wizard_import", event_slug=self.event.slug,
                        import_slug=form.cleaned_data["import_event"].slug)


class NewEventWizardImportView(EventSlugMixin, NewEventWizardMixin, FormView):
    """
    Wizard view: Select configuration elements to copy

    Displays lists of requirements, categories and dashboard buttons that the user can select entries to be copied from

    Afterwards, the event can be activated in :class:`NewEventWizardActivateView`
    """
    form_class = NewEventWizardImportForm
    template_name = "admin/AKModel/event_wizard/import.html"
    wizard_step = 4
    # Configuration steps (phase, step) whose progress is tracked when copying elements of the given type
    tracked_import_steps = {
        "import_categories": ("configuration", "categories"),
        "import_requirements": ("configuration", "requirements"),
    }

    def get_initial(self):
        initial = super().get_initial()
        # Remember which event was selected and send it again when submitting the form for validation
        initial["import_event"] = Event.objects.get(slug=self.kwargs["import_slug"])
        return initial

    def form_valid(self, form):
        # pylint: disable=consider-using-f-string
        import_types = ["import_categories", "import_requirements"]
        if apps.is_installed("AKDashboard"):
            import_types.append("import_buttons")

        # Loop over all kinds of configuration elements and then over all selected elements of each type
        # and try to clone them by requesting a new primary key, adapting the event and then storing the
        # object in the database
        for import_type in import_types:
            copied, failed = [], []
            for import_obj in form.cleaned_data.get(import_type):
                try:
                    import_obj.event = self.event
                    import_obj.pk = None
                    import_obj.save()
                    copied.append(str(import_obj))
                    messages.add_message(self.request, messages.SUCCESS, _("Copied '%(obj)s'" % {'obj': import_obj}))
                except BaseException as e:  # pylint: disable=broad-exception-caught
                    failed.append(str(import_obj))
                    messages.add_message(self.request, messages.ERROR,
                                         _("Could not copy '%(obj)s' (%(error)s)" % {'obj': import_obj,
                                                                                     "error": str(e)}))
            if import_type in self.tracked_import_steps:
                self._record_import_progress(self.tracked_import_steps[import_type], form.initial["import_event"],
                                             copied, failed)
        return redirect("admin:new_event_wizard_activate", slug=self.event.slug)

    def _record_import_progress(self, step: tuple[str, str], import_event: Event, copied: list[str],
                                failed: list[str]):
        """
        Track the progress of a configuration step after copying the corresponding elements

        Nothing is recorded if no elements of this type were selected (the step can still be done manually).
        The step is done if all selected elements were copied and failed otherwise.

        :param step: phase and step key of the step to track
        :param import_event: event the elements were copied from
        :param copied: names of the elements copied successfully
        :param failed: names of the elements that could not be copied
        """
        if not copied and not failed:
            return
        detail = _("Copied from %(event)s: %(copied)s") % {"event": import_event, "copied": ", ".join(copied)} \
            if copied else ""
        if failed:
            detail += ("\n" if detail else "") \
                      + _("Could not copy: %(failed)s") % {"failed": ", ".join(failed)}
        status_tracker.record(self.event, *step,
                              Progress.FAILED if failed else Progress.DONE,
                              detail=detail)


class NewEventWizardActivateView(NewEventWizardMixin, UpdateView):
    """
    Wizard view: Allow activating the event

    The user is asked to make the created event active. This is done in this step and not already during the creation
    in the second step of the wizard to prevent users seeing an unconfigured submission.
    The event will nevertheless already be visible in the dashboard before, when a public event was created in
    :class:`NewEventWizardSettingsView`.

    In the following last step (:class:`NewEventWizardFinishView`), a confirmation of the full process and some
    details of the created event are shown

    The activation is tracked automatically (see :func:`AKModel.signals.track_event_activation`)
    """
    model = Event
    template_name = "admin/AKModel/event_wizard/activate.html"
    form_class = NewEventWizardActivateForm
    wizard_step = 5

    def get_success_url(self):
        return reverse_lazy("admin:new_event_wizard_finish", kwargs={"slug": self.object.slug})


class NewEventWizardFinishView(NewEventWizardMixin, DetailView):
    """
    Wizard view: Confirmation and summary

    Show a confirmation and a summary of the created event
    """
    model = Event
    template_name = "admin/AKModel/event_wizard/finish.html"
    wizard_step = 6
