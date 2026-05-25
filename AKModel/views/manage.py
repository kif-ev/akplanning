import datetime
import json
import os
import tempfile
from itertools import zip_longest
from urllib.parse import urlencode

from django.contrib import messages
from django.core import signing
from django.db.models.functions import Now
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView
from django_tex.core import render_template_with_context, run_tex_in_directory
from django_tex.response import PDFResponse

from AKModel.availability.models import Availability
from AKModel.forms import DefaultSlotCategoriesForm, DefaultSlotEditorForm, ShiftByOffsetForm, SlideExportForm
from AKModel.metaviews.admin import AdminViewMixin, EventSlugMixin, IntermediateAdminActionView, IntermediateAdminView
from AKModel.models import AKCategory, AKOwner, AKSlot, AKType, ConstraintViolation, DefaultSlot, Event


class UserView(TemplateView):
    """
    View: Start page for logged in user

    Will over a link to backend or inform the user that their account still needs to be confirmed
    """
    template_name = "AKModel/user.html"


def _parse_selected_ids(values):
    return [int(value) for value in values if str(value).strip() != ""]


def _build_slide_export_context(*, event, num_next, presentation_mode, types_ids, types_all_selected_only,
                                categories_ids):
    """Build the context used by both the admin config and the public slides page."""

    def build_ak_list_with_next_aks(ak_list):
        """
        Create a list of tuples cosisting of an AK and a list of upcoming AKs (list length depending on setting)
        """
        if num_next <= 0:
            return [(ak, []) for ak in ak_list]
        next_aks_list = zip_longest(*[ak_list[i + 1:] for i in range(num_next)], fillvalue=None)
        return list(zip_longest(ak_list, next_aks_list, fillvalue=[]))

    # Create a list of types to filter AKs by (if at least one type was selected)
    types = None
    types_filter_string = ""
    show_types = event.aktype_set.count() > 0
    available_type_count = event.aktype_set.count()
    if types_ids and len(types_ids) < available_type_count:
        types = AKType.objects.filter(id__in=types_ids)
        names_string = ', '.join(AKType.objects.get(pk=t).name for t in types_ids)
        types_filter_string = f"[{_('Type(s)')}: {names_string}]"

    categories = None
    if categories_ids:
        categories = AKCategory.objects.filter(id__in=categories_ids)

    # Get all relevant AKs (wishes separately, and either all AKs or only those who should directly or indirectly
    # be presented when restriction setting was chosen)
    categories_with_aks = event.get_categories_with_aks(filter_func=lambda
        ak: not presentation_mode or (ak.present or (ak.present is None and ak.category.present_by_default)),
                                                        types=types,
                                                        types_all_selected_only=types_all_selected_only,
                                                        sort_func=lambda ak: ak.wish,
                                                        categories=categories)

    slides = [{
        'kind': 'title',
        'event_name': event.name,
        'subtitle': _("AKs") + " " + types_filter_string,
    }]
    for category, ak_list in categories_with_aks:
        ak_list_with_next = build_ak_list_with_next_aks(ak_list)
        if len(ak_list_with_next) == 0:
            continue

        slides.append({
            'kind': 'chapter',
            'category': category,
        })

        for ak, next_aks in ak_list_with_next:
            slides.append({
                'kind': 'ak',
                'category': category,
                'ak': ak,
                'next_aks': next_aks,
            })

    return {
        'title': event.name,
        'event_name': event.name,
        'categories_with_aks': [(category, build_ak_list_with_next_aks(ak_list)) for category, ak_list in
                                categories_with_aks],
        'slides': slides,
        'subtitle': _("AKs") + " " + types_filter_string,
        'result_presentation_mode': presentation_mode,
        'show_types': show_types,
    }


class ExportSlidesView(EventSlugMixin, IntermediateAdminView):
    """
    View: Export slides to present AKs

    Over a form to choose some settings for the export and then render the slide content in the browser or as PDF
    """
    title = _('Export AK Slides')
    form_class = SlideExportForm
    template_name = 'admin/AKModel/export/slides.html'
    tex_template_name = 'admin/AKModel/export/slides.tex'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_name"] = self.event.name
        context["default_export_mode"] = self.request.GET.get("export_mode", "pdf")
        return context

    def get_form(self, form_class=None):
        # Filter type choices to those of the current event
        # or completely hide the field if no types are specified for this event
        form = super().get_form(form_class)
        form.fields['categories'].choices = [
            (ak_category.id, ak_category.name) for ak_category in self.event.akcategory_set.all()
        ]
        form.initial['categories'] = [c for (c, _) in form.fields['categories'].choices]
        if self.event.aktype_set.count() > 0:
            form.fields['types'].choices = [
                (ak_type.id, ak_type.name) for ak_type in self.event.aktype_set.all()
            ]
            form.initial['types'] = [c for (c, _) in form.fields['types'].choices]
        else:
            form.fields['types'].widget = form.fields['types'].hidden_widget()
            form.fields['types_all_selected_only'].widget = form.fields['types_all_selected_only'].hidden_widget()
        return form

    def _build_public_url(self, form):
        public_url = reverse("model:ak_slides_public", kwargs={"event_slug": self.event.slug})
        config = signing.dumps({
            "num_next": form.cleaned_data["num_next"],
            "presentation_mode": form.cleaned_data["presentation_mode"],
            "types": form.cleaned_data["types"],
            "types_all_selected_only": form.cleaned_data["types_all_selected_only"],
            "categories": form.cleaned_data["categories"],
        })
        return f"{public_url}?{urlencode({'config': config})}"

    def _build_pdf_response(self, form):
        context = _build_slide_export_context(
                event=self.event,
                num_next=form.cleaned_data["num_next"],
                presentation_mode=form.cleaned_data["presentation_mode"],
                types_ids=_parse_selected_ids(form.cleaned_data["types"]),
                types_all_selected_only=form.cleaned_data["types_all_selected_only"],
                categories_ids=_parse_selected_ids(form.cleaned_data["categories"]),
        )
        context['translations'] = {
            'symbols': _("Symbols"),
            'who': _("Who?"),
            'duration': _("Duration(s)"),
            'reso': _("Reso intention?"),
            'wish': _("Wish"),
            'types': _("Types"),
            'goal': _("Design/Goal"),
        }

        source = render_template_with_context(self.tex_template_name, context)

        # Perform real compilation (run latex twice for correct page numbers)
        with tempfile.TemporaryDirectory() as tempdir:
            run_tex_in_directory(source, tempdir, template_name=self.tex_template_name)
            os.remove(f'{tempdir}/texput.tex')
            pdf = run_tex_in_directory(source, tempdir, template_name=self.tex_template_name)

        # Show PDF file to the user (with a filename containing a timestamp to prevent confusions about the right
        # version to use when generating multiple versions of the slides, e.g., because owners did last-minute changes
        # to their AKs
        timestamp = datetime.datetime.now(tz=self.event.timezone).strftime("%Y-%m-%d_%H_%M")
        return PDFResponse(pdf, filename=f'{self.event.slug}_ak_slides_{timestamp}.pdf')

    def form_valid(self, form):
        if self.request.POST.get("export_mode", self.request.GET.get("export_mode", "pdf")) == "web":
            return HttpResponseRedirect(self._build_public_url(form))
        return self._build_pdf_response(form)


class PublishedSlidesView(EventSlugMixin, TemplateView):
    """Public slides view for an event."""
    template_name = "AKModel/slides_carousel.html"

    def get(self, request, *args, **kwargs):
        config = request.GET.get("config")
        if config:
            try:
                self.config_data = signing.loads(config)
            except signing.BadSignature:
                messages.warning(request, _('Invalid export config, please try again.'))
                return HttpResponseRedirect(reverse("admin:ak_slide_export", kwargs={"event_slug": self.event.slug}))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update(_build_slide_export_context(
                event=self.event,
                num_next=int(self.config_data.get("num_next", 3)),
                presentation_mode=bool(self.config_data.get("presentation_mode", False)),
                types_ids=_parse_selected_ids(self.config_data["types"]) if "types" in self.config_data else None,
                types_all_selected_only=bool(self.config_data.get("types_all_selected_only", False)),
                categories_ids=_parse_selected_ids(
                        self.config_data["categories"]) if "categories" in self.config_data else None,
        ))
        return context


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


class ClearScheduleView(IntermediateAdminActionView, ListView):
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

    def get_queryset(self, *args, **kwargs):
        query_set = super().get_queryset(*args, **kwargs)
        # do not reset fixed AKs
        query_set = query_set.filter(fixed=False)
        return query_set

    def action(self, form):
        """Reset rooms and start for all selected slots."""
        self.entities.update(room=None, start=None)


class AvailabilitiesApplyOffsetView(IntermediateAdminActionView, ListView):
    """
    Admin action view: Shift Availabilities
    """
    title = _('Shift availabilities')
    model = Availability
    confirmation_message = _('Shift the following availabilities by the specified offset')
    success_message = _('Availabilities shifted')
    form_class = ShiftByOffsetForm

    def action(self, form):
        """Shift availabilities by given offset."""
        offset = datetime.timedelta(hours=float(form.cleaned_data['offset_hours']))
        for availability in self.entities:
            availability.start = availability.start + offset
            availability.end = availability.end + offset
            availability.save()


class SlotsApplyOffsetView(IntermediateAdminActionView, ListView):
    """
    Admin action view: Shift slots
    """
    title = _('Shift slots')
    model = AKSlot
    confirmation_message = _('Shift the following AKSlots by the specified offset')
    success_message = _('Slots shifted')
    form_class = ShiftByOffsetForm

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset(*args, **kwargs).filter(start__isnull=False)

    def action(self, form):
        """Shift slots by given offset."""
        offset = datetime.timedelta(hours=float(form.cleaned_data['offset_hours']))
        for slot in self.entities:
            slot.start = slot.start + offset
            slot.save()


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


class DefaultSlotCategoryBulkAssignmentView(IntermediateAdminActionView):
    """
    Admin action view: Publish the preference poll of one or multitple event(s)
    """
    title = _('Assign primary categories to default slots')
    model = DefaultSlot
    confirmation_message = _('Assign primary categories in bulk for the following slots, '
                             'this will reset all existing categories. Selected slots:')
    success_message = _('Categories assigned')
    form_class = DefaultSlotCategoriesForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = DefaultSlot.objects.get(pk=kwargs["initial"]["pks"].split(",")[0]).event
        return kwargs

    def action(self, form):
        """Assign categories."""
        categories = form.cleaned_data['primary_categories']
        for slot in self.entities:
            slot.primary_categories.clear()
            slot.primary_categories.set(categories)


class AKsByUserView(AdminViewMixin, EventSlugMixin, DetailView):
    """
    View: Show all AKs of a given user
    """
    model = AKOwner
    context_object_name = 'owner'
    template_name = "admin/AKModel/aks_by_user.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["aks"] = self.object.ak_set.select_related('event')
        context["akslots"] = AKSlot.objects.filter(ak__owners=self.object).select_related('ak', 'room').all()
        context["availabilities"] = []
        context["title_in_cal"] = "akname"
        return context
