import datetime
import json
from itertools import zip_longest
from urllib.parse import urlencode

from django.contrib import messages
from django.core import signing
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView

from AKModel.availability.models import Availability
from AKModel.forms import CVMarkResolvedForm, DefaultSlotCategoriesForm, DefaultSlotEditorForm, ShiftByOffsetForm, \
    SlideExportForm
from AKModel.metaviews.admin import AdminViewMixin, EventSlugMixin, IntermediateAdminActionView, IntermediateAdminView
from AKModel.models import AKCategory, AKOwner, AKSlot, AKType, ConstraintViolation, DefaultSlot, Event, \
    StatusTrackingEntry
from AKModel.status_tracking import status_tracker

Progress = StatusTrackingEntry.Progress


class UserView(TemplateView):
    """
    View: Start page for logged in user

    Will over a link to backend or inform the user that their account still needs to be confirmed
    """
    template_name = "AKModel/user.html"


def _parse_selected_ids(values):
    return [int(value) for value in values if str(value).strip() != ""]


def _serialize_datetime(value):
    """
    Serialize an (optional) datetime for the signed slide config (which only supports JSON types)

    :param value: datetime to serialize or None
    :return: ISO representation of the datetime or None
    :rtype: str | None
    """
    return value.isoformat() if value else None


def _parse_config_datetime(value):
    """
    Parse an (optional) datetime from the signed slide config, counterpart to :func:`_serialize_datetime`

    :param value: ISO representation of a datetime, None or missing (configs created before the timespan filter)
    :return: parsed datetime or None
    :rtype: datetime.datetime | None
    """
    return parse_datetime(value) if value else None


def _truncate_to_minute(value):
    """
    Remove seconds and microseconds from a datetime

    Needed to compare user input with event start and end, since the date picker does not support seconds

    :param value: datetime to truncate
    :return: truncated datetime
    :rtype: datetime.datetime
    """
    return value.replace(second=0, microsecond=0)


def _ak_has_slot_in_timespan(ak, timespan_start, timespan_end):
    """
    Check whether an AK has at least one scheduled slot overlapping with the given timespan

    Slots only touching the timespan (e.g., ending exactly at its start) do not count as overlapping.
    Unscheduled slots (without start) are ignored.

    :param ak: AK to check (slots should be prefetched to prevent additional queries)
    :type ak: AK
    :param timespan_start: start of the timespan
    :type timespan_start: datetime.datetime
    :param timespan_end: end of the timespan
    :type timespan_end: datetime.datetime
    :return: True if at least one slot overlaps the timespan, False otherwise
    :rtype: bool
    """
    return any(slot.start is not None and slot.start < timespan_end and slot.end > timespan_start
               for slot in ak.akslot_set.all())


def _build_slide_legend(slides, *, show_types, presentation_mode):
    """
    Build the legend for the title slide, only containing the pictograms that are actually used on the AK slides
    (conditions mirror those in the slide template)

    :param slides: slides as created by ``_build_slide_export_context``
    :type slides: list[dict]
    :param show_types: are types shown on the slides?
    :type show_types: bool
    :param presentation_mode: are the slides created in presentation mode (without durations)?
    :type presentation_mode: bool
    :return: list of tuples consisting of icon name and label
    :rtype: list[(str, str)]
    """
    ak_slides = [slide for slide in slides if slide['kind'] == 'ak']
    legend_entries = [
        ("magic", _("Wish"), any(s['ak'].wish for s in ak_slides)),
        ("scroll", _("Resolution Intention"), any(s['ak'].reso for s in ak_slides)),
        ("user", _("Owners"), any(not s['ak'].wish for s in ak_slides)),
        ("list", _("Types"), show_types and any(s['ak'].types_list for s in ak_slides)),
        ("clock", _("Duration(s)"),
         not presentation_mode and any(s['ak'].durations_list for s in ak_slides)),
        ("bullseye", _("Design/Goal"), any(s['ak'].goal for s in ak_slides)),
        ("angles-right", _("Upcoming AKs"), any(s['next_aks'] for s in ak_slides)),
    ]
    return [(icon, label) for icon, label, used in legend_entries if used]


def _build_slide_export_context(*, event, num_next, presentation_mode, types_ids, types_all_selected_only,
                                categories_ids, include_wishes=True, timespan=(None, None)):
    """
    Build the context used by both the admin config and the public slides page.

    The timespan is given as tuple of start and end (each may be None to use the event's start or end).
    If the given timespan deviates from the event's start and end, only AKs with at least one slot in that timespan
    are included and the timespan is shown on the title slide. When the timespan covers the whole event (default),
    no filtering is applied, so AKs that are not scheduled yet are still included (e.g., when presenting AKs
    before the scheduling is done).

    Whether wishes are included is controlled solely by ``include_wishes``, i.e., wishes are neither removed by the
    presentation mode nor by the timespan (category and type filters still apply).
    """
    # Default to the full event if no (or only a partial) timespan was given
    timespan_start = timespan[0] or event.start
    timespan_end = timespan[1] or event.end
    # Compare with minute precision since the date picker does not allow to input seconds
    timespan_changed = (_truncate_to_minute(timespan_start) != _truncate_to_minute(event.start)
                        or _truncate_to_minute(timespan_end) != _truncate_to_minute(event.end))
    timespan_string = ""
    if timespan_changed:
        # Use the simplified format (weekday + time, e.g. "Fri 14:00") also used for slots
        timespan_string = (f"{_('Timespan')}: "
                           f"{date_format(timespan_start.astimezone(event.timezone), format='D G:i', use_l10n=True)}"
                           f" - "
                           f"{date_format(timespan_end.astimezone(event.timezone), format='D G:i', use_l10n=True)}")

    def include_ak(ak):
        """
        Filter predicate: Should the given AK be included in the slides?

        Wishes are included or excluded depending only on the explicit wish setting. For all other AKs,
        respects the presentation mode (only AKs that should directly or indirectly be presented)
        and the timespan (only if it deviates from the full event)
        """
        if ak.wish:
            return include_wishes
        if presentation_mode and not (ak.present or (ak.present is None and ak.category.present_by_default)):
            return False
        return not timespan_changed or _ak_has_slot_in_timespan(ak, timespan_start, timespan_end)

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
    if types_ids and len(types_ids) < event.aktype_set.count():
        types = AKType.objects.filter(id__in=types_ids)
        types_filter_string = f"[{_('Type(s)')}: {', '.join(AKType.objects.get(pk=t).name for t in types_ids)}]"

    categories = None
    if categories_ids:
        categories = AKCategory.objects.filter(id__in=categories_ids)

    # Get all relevant AKs (wishes separately, and either all AKs or only those who should directly or indirectly
    # be presented when restriction setting was chosen, optionally restricted to the chosen timespan)
    categories_with_aks = event.get_categories_with_aks(filter_func=include_ak,
                                                        types=types,
                                                        types_all_selected_only=types_all_selected_only,
                                                        sort_func=lambda ak: ak.wish,
                                                        categories=categories)

    slides = [{
        'kind': 'title',
        'event_name': event.name,
        'subtitle': _("AKs") + " " + types_filter_string,
        'timespan': timespan_string,
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
        'timespan': timespan_string,
        'result_presentation_mode': presentation_mode,
        'show_types': show_types,
        'legend': _build_slide_legend(slides, show_types=show_types, presentation_mode=presentation_mode),
    }


class ExportSlidesView(EventSlugMixin, IntermediateAdminView):
    """
    View: Export slides to present AKs

    Over a form to choose some settings for the export and then show the slides in the web carousel or in a print view
    of the carousel slides, which can be saved as PDF by the browser
    """
    title = _('Export AK Slides')
    form_class = SlideExportForm
    template_name = 'admin/AKModel/export/slides.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_name"] = self.event.name
        context["default_export_mode"] = self.request.GET.get("export_mode", "pdf")
        return context

    def get_form(self, form_class=None):
        # Filter type choices to those of the current event
        # or completely hide the field if no types are specified for this event
        # Use the timezone of the event to display and parse the timespan fields
        timezone.activate(self.event.timezone)
        form = super().get_form(form_class)
        # Default timespan: the whole event
        form.initial['timespan'] = (self.event.start, self.event.end)
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

    def _build_public_url(self, form, url_name="model:ak_slides_public"):
        public_url = reverse(url_name, kwargs={"event_slug": self.event.slug})
        timespan_start, timespan_end = form.cleaned_data["timespan"]
        config = signing.dumps({
            "num_next": form.cleaned_data["num_next"],
            "presentation_mode": form.cleaned_data["presentation_mode"],
            "include_wishes": form.cleaned_data["include_wishes"],
            "types": form.cleaned_data["types"],
            "types_all_selected_only": form.cleaned_data["types_all_selected_only"],
            "categories": form.cleaned_data["categories"],
            "timespan_start": _serialize_datetime(timespan_start),
            "timespan_end": _serialize_datetime(timespan_end),
        })
        return f"{public_url}?{urlencode({'config': config})}"

    def form_valid(self, form):
        export_mode = self.request.POST.get("export_mode", self.request.GET.get("export_mode", "pdf"))
        if export_mode == "web":
            return HttpResponseRedirect(self._build_public_url(form))
        # The PDF is created by the browser from the print view of the web carousel slides
        return HttpResponseRedirect(self._build_public_url(form, url_name="model:ak_slides_pdf"))


class PublishedSlidesView(EventSlugMixin, TemplateView):
    """Public slides view for an event."""
    template_name = "AKModel/slides_carousel.html"

    def get(self, request, *args, **kwargs):
        config = request.GET.get("config")
        if config:
            try:
                self.config_data = signing.loads(config)  # pylint: disable=attribute-defined-outside-init
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
                include_wishes=bool(self.config_data.get("include_wishes", True)),
                types_ids=_parse_selected_ids(self.config_data["types"]) if "types" in self.config_data else None,
                types_all_selected_only=bool(self.config_data.get("types_all_selected_only", False)),
                categories_ids=_parse_selected_ids(
                        self.config_data["categories"]) if "categories" in self.config_data else None,
                timespan=(_parse_config_datetime(self.config_data.get("timespan_start")),
                          _parse_config_datetime(self.config_data.get("timespan_end"))),
        ))
        return context


class PublishedSlidesPDFView(PublishedSlidesView):
    """
    Print view of the public slides for an event

    Shows all slides of the web carousel below each other, laid out as 16:9 pages when printing,
    so they can be saved as PDF using the print dialog of the browser (without any server-side PDF rendering)
    """
    template_name = "AKModel/slides_pdf.html"


class CVMarkResolvedView(IntermediateAdminActionView):
    """
    Admin action view: Mark one or multitple constraint violation(s) as resolved

    Asks for an (optional) reason and stores it together with the user who marked the violations as resolved
    """
    title = _('Mark Constraint Violations as manually resolved')
    model = ConstraintViolation
    form_class = CVMarkResolvedForm
    confirmation_message = _("The following Constraint Violations will be marked as manually resolved")
    success_message = _("Constraint Violations marked as resolved")

    def action(self, form):
        self.entities.update(manually_resolved=True,
                             resolution_reason=form.cleaned_data['resolution_reason'],
                             resolved_by=self.request.user)


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
        self.entities.update(plan_published_at=timezone.now(), plan_hidden=False)
        for event in self.entities:
            status_tracker.record_if_registered(event, "scheduling", "publish_plan", Progress.DONE,
                                                detail=str(self.success_message))


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
        # The plan has to be published again, hence the step is no longer done
        for event in self.entities:
            status_tracker.record_if_registered(event, "scheduling", "publish_plan", Progress.IN_PROGRESS,
                                                detail=str(self.success_message))


class PollPublishView(IntermediateAdminActionView):
    """
    Admin action view: Publish the preference poll of one or multitple event(s)
    """
    title = _('Publish preference poll')
    model = Event
    confirmation_message = _('Publish the poll(s) of:')
    success_message = _('Preference poll published')

    def action(self, form):
        self.entities.update(poll_published_at=timezone.now(), poll_hidden=False)


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = [
            {"id": c.id, "name": c.name}
            for c in AKCategory.objects.filter(event=self.event).order_by("name")
        ]
        return context

    def get_initial(self):
        initial = super().get_initial()
        default_slots = [
            {
                "id": s.id,
                "start": s.start_iso,
                "end": s.end_iso,
                "allDay": False,
                "categories": [c.id for c in s.primary_categories.all()],
            }
            for s in self.event.defaultslot_set.prefetch_related("primary_categories")
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
        event_categories = {c.id: c for c in AKCategory.objects.filter(event=self.event)}

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
                new_slot = DefaultSlot.objects.create(
                        start=start,
                        end=end,
                        event=self.event
                )
                # Assign primary categories (only those belonging to this event, ignore invalid entries)
                category_ids = set()
                for c_id in slot.get("categories", []):
                    try:
                        category_ids.add(int(c_id))
                    except (TypeError, ValueError):
                        continue
                new_slot.primary_categories.set(
                        [event_categories[c_id] for c_id in category_ids if c_id in event_categories]
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
