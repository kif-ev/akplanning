import datetime
import json
import os
import tempfile
from itertools import zip_longest

from django.contrib import messages
from django.db.models import Q
from django.db.models.functions import Now
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView
from django_tex.core import render_template_with_context, run_tex_in_directory
from django_tex.response import PDFResponse

from AKModel.forms import SlideExportForm, DefaultSlotEditorForm
from AKModel.metaviews.admin import EventSlugMixin, FilterByEventSlugMixin, \
    IntermediateAdminView, IntermediateAdminActionView, AdminViewMixin
from AKModel.models import ConstraintViolation, Event, DefaultSlot, AKOwner, AKSlot, AKType


class UserView(TemplateView):
    """
    View: Start page for logged in user

    Will over a link to backend or inform the user that their account still needs to be confirmed
    """
    template_name = "AKModel/user.html"


class ExportSlidesView(EventSlugMixin, IntermediateAdminView):
    """
    View: Export slides to present AKs

    Over a form to choose some settings for the export and then generate the PDF
    """
    title = _('Export AK Slides')
    form_class = SlideExportForm

    def get_form(self, form_class=None):
        # Filter type choices to those of the current event
        # or completely hide the field if no types are specified for this event
        form = super().get_form(form_class)
        if self.event.aktype_set.count() > 0:
            form.fields['types'].choices = [
                (ak_type.id, ak_type.name) for ak_type in self.event.aktype_set.all()
            ]
        else:
            form.fields['types'].widget = form.fields['types'].hidden_widget()
            form.fields['types_all_selected_only'].widget = form.fields['types_all_selected_only'].hidden_widget()
        return form

    def form_valid(self, form):
        # pylint: disable=invalid-name
        template_name = 'admin/AKModel/export/slides.tex'

        # Settings
        NEXT_AK_LIST_LENGTH = form.cleaned_data['num_next']
        RESULT_PRESENTATION_MODE = form.cleaned_data["presentation_mode"]
        SPACE_FOR_NOTES_IN_WISHES = form.cleaned_data["wish_notes"]

        translations = {
            'symbols': _("Symbols"),
            'who': _("Who?"),
            'duration': _("Duration(s)"),
            'reso': _("Reso intention?"),
            'category': _("Category (for Wishes)"),
            'wishes': _("Wishes"),
            'types': _("Types"),
        }

        def build_ak_list_with_next_aks(ak_list):
            """
            Create a list of tuples cosisting of an AK and a list of upcoming AKs (list length depending on setting)
            """
            next_aks_list = zip_longest(*[ak_list[i + 1:] for i in range(NEXT_AK_LIST_LENGTH)], fillvalue=None)
            return list(zip_longest(ak_list, next_aks_list, fillvalue=[]))

        # Create a list of types to filter AKs by (if at least one type was selected)
        types = None
        types_filter_string = ""
        show_types = self.event.aktype_set.count() > 0
        if len(form.cleaned_data['types']) > 0:
            types = AKType.objects.filter(id__in=form.cleaned_data['types'])
            names_string = ', '.join(AKType.objects.get(pk=t).name for t in form.cleaned_data['types'])
            types_filter_string = f"[{_('Type(s)')}: {names_string}]"
        types_all_selected_only = form.cleaned_data['types_all_selected_only']

        # Get all relevant AKs (wishes separately, and either all AKs or only those who should directly or indirectly
        # be presented when restriction setting was chosen)
        categories_with_aks, ak_wishes = self.event.get_categories_with_aks(wishes_seperately=True, filter_func=lambda
            ak: not RESULT_PRESENTATION_MODE or (ak.present or (ak.present is None and ak.category.present_by_default)),
                                                                    types=types,
                                                                    types_all_selected_only=types_all_selected_only)

        # Create context for LaTeX rendering
        context = {
            'title': self.event.name,
            'categories_with_aks': [(category, build_ak_list_with_next_aks(ak_list)) for category, ak_list in
                                    categories_with_aks],
            'subtitle': _("AKs") + " " + types_filter_string,
            "wishes": build_ak_list_with_next_aks(ak_wishes),
            "translations": translations,
            "result_presentation_mode": RESULT_PRESENTATION_MODE,
            "space_for_notes_in_wishes": SPACE_FOR_NOTES_IN_WISHES,
            "show_types": show_types,
        }

        source = render_template_with_context(template_name, context)

        # Perform real compilation (run latex twice for correct page numbers)
        with tempfile.TemporaryDirectory() as tempdir:
            run_tex_in_directory(source, tempdir, template_name=self.template_name)
            os.remove(f'{tempdir}/texput.tex')
            pdf = run_tex_in_directory(source, tempdir, template_name=self.template_name)

        # Show PDF file to the user (with a filename containing a timestamp to prevent confusions about the right
        # version to use when generating multiple versions of the slides, e.g., because owners did last-minute changes
        # to their AKs
        timestamp = datetime.datetime.now(tz=self.event.timezone).strftime("%Y-%m-%d_%H_%M")
        return PDFResponse(pdf, filename=f'{self.event.slug}_ak_slides_{timestamp}.pdf')


class CVMarkResolvedView(IntermediateAdminActionView):
    """
    Admin action view: Mark one or multitple constraint violation(s) as resolved
    """
    title = _('Mark Constraint Violations as manually resolved')
    model = ConstraintViolation
    confirmation_message = _("The following Constraint Violations will be marked as manually resolved")
    success_message = _("Constraint Violations marked as resolved")

    def action(self, form):
        self.entities.update(manually_resolved=True)


class CVSetLevelViolationView(IntermediateAdminActionView):
    """
    Admin action view: Set one or multitple constraint violation(s) as to level "violation"
    """
    title = _('Set Constraint Violations to level "violation"')
    model = ConstraintViolation
    confirmation_message = _("The following Constraint Violations will be set to level 'violation'")
    success_message = _("Constraint Violations set to level 'violation'")

    def action(self, form):
        self.entities.update(level=ConstraintViolation.ViolationLevel.VIOLATION)


class CVSetLevelWarningView(IntermediateAdminActionView):
    """
    Admin action view: Set one or multitple constraint violation(s) as to level "warning"
    """
    title = _('Set Constraint Violations to level "warning"')
    model = ConstraintViolation
    confirmation_message = _("The following Constraint Violations will be set to level 'warning'")
    success_message = _("Constraint Violations set to level 'warning'")

    def action(self, form):
        self.entities.update(level=ConstraintViolation.ViolationLevel.WARNING)

class ClearScheduleView(FilterByEventSlugMixin, IntermediateAdminView, ListView):
    """
    Admin action view: Clear schedule
    """
    title = _('Clear schedule')
    model = AKSlot
    confirmation_message = _('Clear schedule. The following scheduled AKSlots will be reset')
    success_message = _('Schedule cleared')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entities = AKSlot.objects.none()

    def get_queryset(self):
        query_set = super().get_queryset()
        query_set = query_set.filter(fixed=False)
        query_set = query_set.filter(Q(room__isnull=False) | Q(start__isnull=False))
        return query_set

    def action(self):
        """Reset rooms and start for all selected slots."""
        self.entities.update(room=None, start=None)

    def get_preview(self):
        self.entities = self.get_queryset()
        joined_entities = '\n'.join(str(e) for e in self.entities)
        return f"{self.confirmation_message}:\n\n {joined_entities}"

    def form_valid(self, form):
        self.entities = self.get_queryset()
        self.action()
        messages.add_message(self.request, messages.SUCCESS, self.success_message)
        return redirect("admin:event_status", self.event.slug)

class PlanPublishView(IntermediateAdminActionView):
    """
    Admin action view: Publish the plan of one or multitple event(s)
    """
    title = _('Publish plan')
    model = Event
    confirmation_message = _('Publish the plan(s) of:')
    success_message = _('Plan published')

    def action(self, form):
        self.entities.update(plan_published_at=Now(), plan_hidden=False)


class PlanUnpublishView(IntermediateAdminActionView):
    """
    Admin action view: Unpublish the plan of one or multitple event(s)
    """
    title = _('Unpublish plan')
    model = Event
    confirmation_message = _('Unpublish the plan(s) of:')
    success_message = _('Plan unpublished')

    def action(self, form):
        self.entities.update(plan_published_at=None, plan_hidden=True)


class PollPublishView(IntermediateAdminActionView):
    """
    Admin action view: Publish the preference poll of one or multitple event(s)
    """
    title = _('Publish preference poll')
    model = Event
    confirmation_message = _('Publish the poll(s) of:')
    success_message = _('Preference poll published')

    def action(self, form):
        self.entities.update(poll_published_at=Now(), poll_hidden=False)


class PollUnpublishView(IntermediateAdminActionView):
    """
    Admin action view: Unpublish the preference poll of one or multitple event(s)
    """
    title = _('Unpublish preference poll')
    model = Event
    confirmation_message = _('Unpublish the preference poll(s) of:')
    success_message = _('Preference poll unpublished')

    def action(self, form):
        self.entities.update(poll_published_at=None, poll_hidden=True)

class DefaultSlotEditorView(EventSlugMixin, IntermediateAdminView):
    """
    Admin view: Allow to edit the default slots of an event
    """
    template_name = "admin/AKModel/default_slot_editor.html"
    form_class = DefaultSlotEditorForm
    title = _("Edit Default Slots")

    def get_success_url(self):
        return self.request.path

    def get_initial(self):
        initial = super().get_initial()
        default_slots = [
            {"id": s.id, "start": s.start_iso, "end": s.end_iso, "allDay": False}
            for s in self.event.defaultslot_set.all()
        ]
        initial['availabilities'] = json.dumps({
            'availabilities': default_slots
        })
        return initial

    def form_valid(self, form):
        default_slots_raw = json.loads(form.cleaned_data['availabilities'])["availabilities"]
        tz = self.event.timezone

        created_count = 0
        updated_count = 0

        previous_slot_ids = set(s.id for s in self.event.defaultslot_set.all())

        # Loop over inputs and update or add slots
        for slot in default_slots_raw:
            start = parse_datetime(slot["start"]).replace(tzinfo=tz)
            end = parse_datetime(slot["end"]).replace(tzinfo=tz)

            if slot["id"] != '':
                slot_id = int(slot["id"])
                if slot_id not in previous_slot_ids:
                    # Make sure only slots (currently) belonging to this event are edited
                    # (user did not manipulate IDs and slots have not been deleted in another session in the meantime)
                    messages.add_message(
                        self.request,
                        messages.WARNING,
                        _("Could not update slot {id} since it does not belong to {event}")
                        .format(id=slot['id'], event=self.event.name)
                    )
                else:
                    # Update existing entries
                    previous_slot_ids.remove(slot_id)
                    original_slot = DefaultSlot.objects.get(id=slot_id)
                    if original_slot.start != start or original_slot.end != end:
                        original_slot.start = start
                        original_slot.end = end
                        original_slot.save()
                        updated_count += 1
            else:
                # Create new entries
                DefaultSlot.objects.create(
                    start=start,
                    end=end,
                    event=self.event
                )
                created_count += 1

        # Delete all slots not re-submitted by the user (and hence deleted in editor)
        deleted_count = len(previous_slot_ids)
        for d_id in previous_slot_ids:
            DefaultSlot.objects.get(id=d_id).delete()

        # Inform user about changes performed
        if created_count + updated_count + deleted_count > 0:
            messages.add_message(
                self.request,
                messages.SUCCESS,
                _("Updated {u} slot(s). created {c} new slot(s) and deleted {d} slot(s)")
                .format(u=str(updated_count), c=str(created_count), d=str(deleted_count))
            )
        return super().form_valid(form)


class AKsByUserView(AdminViewMixin, EventSlugMixin, DetailView):
    """
    View: Show all AKs of a given user
    """
    model = AKOwner
    context_object_name = 'owner'
    template_name = "admin/AKModel/aks_by_user.html"
