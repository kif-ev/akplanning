import csv
import datetime
import json
import os
import tempfile
from abc import ABC, abstractmethod
from itertools import zip_longest

import django.db
from django.apps import apps
from django.contrib import admin, messages
from django.db.models.functions import Now
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, DetailView, ListView, DeleteView, CreateView, FormView, UpdateView
from django_tex.core import render_template_with_context, run_tex_in_directory
from django_tex.response import PDFResponse
from rest_framework import viewsets, permissions, mixins

from AKModel.forms import NewEventWizardStartForm, NewEventWizardSettingsForm, NewEventWizardPrepareImportForm, \
    NewEventWizardImportForm, NewEventWizardActivateForm, AdminIntermediateForm, SlideExportForm, \
    AdminIntermediateActionForm, DefaultSlotEditorForm, RoomBatchCreationForm
from AKModel.models import Event, AK, AKSlot, Room, AKTrack, AKCategory, AKOwner, AKOrgaMessage, AKRequirement, \
    ConstraintViolation, DefaultSlot
from AKModel.serializers import AKSerializer, AKSlotSerializer, RoomSerializer, AKTrackSerializer, AKCategorySerializer, \
    AKOwnerSerializer


class EventSlugMixin:
    """
    Mixin to handle views with event slugs
    """
    event = None

    def _load_event(self):
        # Find event based on event slug
        if self.event is None:
            self.event = get_object_or_404(Event, slug=self.kwargs.get("event_slug", None))

    def get(self, request, *args, **kwargs):
        self._load_event()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._load_event()
        return super().post(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        self._load_event()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self._load_event()
        return super().create(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if self.event is None:
            self._load_event()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        # Add event to context (to make it accessible in templates)
        context["event"] = self.event
        return context


class FilterByEventSlugMixin(EventSlugMixin):
    """
    Mixin to filter different querysets based on a event slug from the request url
    """

    def get_queryset(self):
        # Filter current queryset based on url event slug or return 404 if event slug is invalid
        return super().get_queryset().filter(event=self.event)


class AdminViewMixin:
    site_url = ''
    title = ''

    def get_context_data(self, **kwargs):
        extra = admin.site.each_context(self.request)
        extra.update(super().get_context_data(**kwargs))

        if self.site_url != '':
            extra["site_url"] = self.site_url
        if self.title != '':
            extra["title"] = self.title

        return extra


class AKOwnerViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKOwnerSerializer

    def get_queryset(self):
        return AKOwner.objects.filter(event=self.event)


class AKCategoryViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKCategorySerializer

    def get_queryset(self):
        return AKCategory.objects.filter(event=self.event)


class AKTrackViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                     mixins.DestroyModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKTrackSerializer

    def get_queryset(self):
        return AKTrack.objects.filter(event=self.event)


class AKViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin,
                viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKSerializer

    def get_queryset(self):
        return AK.objects.filter(event=self.event)


class RoomViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = RoomSerializer

    def get_queryset(self):
        return Room.objects.filter(event=self.event)


class AKSlotViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                    mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKSlotSerializer

    def get_queryset(self):
        return AKSlot.objects.filter(event=self.event)


class UserView(TemplateView):
    template_name = "AKModel/user.html"


class EventStatusView(AdminViewMixin, DetailView):
    template_name = "admin/AKModel/status.html"
    model = Event
    context_object_name = "event"
    title = _("Event Status")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unscheduled_slots_count"] = context["event"].akslot_set.filter(start=None).count
        context["site_url"] = reverse_lazy("dashboard:dashboard_event", kwargs={'slug': context["event"].slug})
        context["ak_messages"] = AKOrgaMessage.objects.filter(ak__event=context["event"])
        return context


class AKRequirementOverview(AdminViewMixin, FilterByEventSlugMixin, ListView):
    model = AKRequirement
    context_object_name = "requirements"
    title = _("Requirements for Event")
    template_name = "admin/AKModel/requirements_overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event"] = self.event
        context["site_url"] = reverse_lazy("dashboard:dashboard_event", kwargs={'slug': context["event"].slug})
        return context


class AKCSVExportView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    template_name = "admin/AKModel/ak_csv_export.html"
    model = AKSlot
    context_object_name = "slots"
    title = _("AK CSV Export")

    def get_queryset(self):
        return super().get_queryset().order_by("ak__track")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class AKWikiExportView(AdminViewMixin, DetailView):
    template_name = "admin/AKModel/wiki_export.html"
    model = Event
    context_object_name = "event"
    title = _("AK Wiki Export")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        categories_with_aks, ak_wishes = context["event"].get_categories_with_aks(
            wishes_seperately=True,
            filter=lambda ak: ak.include_in_export
        )

        context["categories_with_aks"] = [(category.name, ak_list) for category, ak_list in categories_with_aks]
        context["categories_with_aks"].append((_("Wishes"), ak_wishes))

        return context


class IntermediateAdminView(AdminViewMixin, FormView):
    template_name = "admin/AKModel/action_intermediate.html"
    form_class = AdminIntermediateForm

    def get_preview(self):
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        context["preview"] = self.get_preview()
        return context


class AKMessageDeleteView(EventSlugMixin, IntermediateAdminView):
    template_name = "admin/AKModel/message_delete.html"
    title = _("Delete AK Orga Messages")

    def get_orga_messages_for_event(self, event):
        return AKOrgaMessage.objects.filter(ak__event=event)

    def get_success_url(self):
        return reverse_lazy('admin:event_status', kwargs={'slug': self.event.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ak_messages"] = self.get_orga_messages_for_event(self.event)
        return context

    def form_valid(self, form):
        self.get_orga_messages_for_event(self.event).delete()
        messages.add_message(self.request, messages.SUCCESS, _("AK Orga Messages successfully deleted"))
        return super().form_valid(form)


class WizardViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["wizard_step"] = self.wizard_step
        context["wizard_steps"] = [
            _("Start"),
            _("Settings"),
            _("Event created, Prepare Import"),
            _("Import categories & requirements"),
            _("Activate?"),
            _("Finish")
        ]
        context["wizard_step_text"] = context["wizard_steps"][self.wizard_step - 1]
        context["wizard_steps_total"] = len(context["wizard_steps"])
        return context


class NewEventWizardStartView(AdminViewMixin, WizardViewMixin, CreateView):
    model = Event
    form_class = NewEventWizardStartForm
    template_name = "admin/AKModel/event_wizard/start.html"
    wizard_step = 1


class NewEventWizardSettingsView(AdminViewMixin, WizardViewMixin, CreateView):
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


class NewEventWizardPrepareImportView(WizardViewMixin, EventSlugMixin, FormView):
    form_class = NewEventWizardPrepareImportForm
    template_name = "admin/AKModel/event_wizard/created_prepare_import.html"
    wizard_step = 3

    def form_valid(self, form):
        # Selected a valid event to import from? Use this to go to next step of wizard
        return redirect("admin:new_event_wizard_import", event_slug=self.event.slug,
                        import_slug=form.cleaned_data["import_event"].slug)


class NewEventWizardImportView(EventSlugMixin, WizardViewMixin, FormView):
    form_class = NewEventWizardImportForm
    template_name = "admin/AKModel/event_wizard/import.html"
    wizard_step = 4

    def get_initial(self):
        initial = super().get_initial()
        initial["import_event"] = Event.objects.get(slug=self.kwargs["import_slug"])
        return initial

    def form_valid(self, form):
        import_types = ["import_categories", "import_requirements"]
        if apps.is_installed("AKDashboard"):
            import_types.append("import_buttons")

        for import_type in import_types:
            for import_obj in form.cleaned_data.get(import_type):
                # clone existing entry
                try:
                    import_obj.event = self.event
                    import_obj.pk = None
                    import_obj.save()
                    messages.add_message(self.request, messages.SUCCESS, _("Copied '%(obj)s'" % {'obj': import_obj}))
                except BaseException as e:
                    messages.add_message(self.request, messages.ERROR,
                                         _("Could not copy '%(obj)s' (%(error)s)" % {'obj': import_obj,
                                                                                     "error": str(e)}))
        return redirect("admin:new_event_wizard_activate", slug=self.event.slug)


class NewEventWizardActivateView(WizardViewMixin, UpdateView):
    model = Event
    template_name = "admin/AKModel/event_wizard/activate.html"
    form_class = NewEventWizardActivateForm
    wizard_step = 5

    def get_success_url(self):
        return reverse_lazy("admin:new_event_wizard_finish", kwargs={"slug": self.object.slug})


class NewEventWizardFinishView(WizardViewMixin, DetailView):
    model = Event
    template_name = "admin/AKModel/event_wizard/finish.html"
    wizard_step = 6


class ExportSlidesView(EventSlugMixin, IntermediateAdminView):
    title = _('Export AK Slides')
    form_class = SlideExportForm

    def form_valid(self, form):
        template_name = 'admin/AKModel/export/slides.tex'

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
        }

        def build_ak_list_with_next_aks(ak_list):
            next_aks_list = zip_longest(*[ak_list[i + 1:] for i in range(NEXT_AK_LIST_LENGTH)], fillvalue=None)
            return [(ak, next_aks) for ak, next_aks in zip_longest(ak_list, next_aks_list, fillvalue=list())]

        categories_with_aks, ak_wishes = self.event.get_categories_with_aks(wishes_seperately=True, filter=lambda
            ak: not RESULT_PRESENTATION_MODE or (ak.present or (ak.present is None and ak.category.present_by_default)))

        context = {
            'title': self.event.name,
            'categories_with_aks': [(category, build_ak_list_with_next_aks(ak_list)) for category, ak_list in
                                    categories_with_aks],
            'subtitle': _("AKs"),
            "wishes": build_ak_list_with_next_aks(ak_wishes),
            "translations": translations,
            "result_presentation_mode": RESULT_PRESENTATION_MODE,
            "space_for_notes_in_wishes": SPACE_FOR_NOTES_IN_WISHES,
        }

        source = render_template_with_context(template_name, context)

        # Perform real compilation (run latex twice for correct page numbers)
        with tempfile.TemporaryDirectory() as tempdir:
            run_tex_in_directory(source, tempdir, template_name=self.template_name)
            os.remove(f'{tempdir}/texput.tex')
            pdf = run_tex_in_directory(source, tempdir, template_name=self.template_name)

        timestamp = datetime.datetime.now(tz=self.event.timezone).strftime("%Y-%m-%d_%H_%M")
        return PDFResponse(pdf, filename=f'{self.event.slug}_ak_slides_{timestamp}.pdf')


class IntermediateAdminActionView(IntermediateAdminView, ABC):
    form_class = AdminIntermediateActionForm
    entities = None

    def get_queryset(self, pks=None):
        if pks is None:
            pks = self.request.GET['pks']
        return self.model.objects.filter(pk__in=pks.split(","))

    def get_initial(self):
        initial = super().get_initial()
        initial['pks'] = self.request.GET['pks']
        return initial

    def get_preview(self):
        self.entities = self.get_queryset()
        joined_entities = '\n'.join(str(e) for e in self.entities)
        return f"{self.confirmation_message}:\n\n {joined_entities}"

    def get_success_url(self):
        return reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")

    @abstractmethod
    def action(self, form):
        pass

    def form_valid(self, form):
        self.entities = self.get_queryset(pks=form.cleaned_data['pks'])
        self.action(form)
        messages.add_message(self.request, messages.SUCCESS, self.success_message)
        return super().form_valid(form)


class LoopActionMixin(ABC):
    def action(self, form):
        self.pre_action()
        for entity in self.entities:
            self.perform_action(entity)
            entity.save()
        self.post_action()

    @abstractmethod
    def perform_action(self, entity):
        pass

    def pre_action(self):
        pass

    def post_action(self):
        pass


class CVMarkResolvedView(IntermediateAdminActionView):
    title = _('Mark Constraint Violations as manually resolved')
    model = ConstraintViolation
    confirmation_message = _("The following Constraint Violations will be marked as manually resolved")
    success_message = _("Constraint Violations marked as resolved")

    def action(self, form):
        self.entities.update(manually_resolved=True)


class CVSetLevelViolationView(IntermediateAdminActionView):
    title = _('Set Constraint Violations to level "violation"')
    model = ConstraintViolation
    confirmation_message = _("The following Constraint Violations will be set to level 'violation'")
    success_message = _("Constraint Violations set to level 'violation'")

    def action(self, form):
        self.entities.update(level=ConstraintViolation.ViolationLevel.VIOLATION)


class CVSetLevelWarningView(IntermediateAdminActionView):
    title = _('Set Constraint Violations to level "warning"')
    model = ConstraintViolation
    confirmation_message = _("The following Constraint Violations will be set to level 'warning'")
    success_message = _("Constraint Violations set to level 'warning'")

    def action(self, form):
        self.entities.update(level=ConstraintViolation.ViolationLevel.WARNING)


class AKResetInterestView(IntermediateAdminActionView):
    title = _("Reset interest in AKs")
    model = AK
    confirmation_message = _("Interest of the following AKs will be set to not filled (-1):")
    success_message = _("Reset of interest in AKs successful.")

    def action(self, form):
        self.entities.update(interest=-1)


class AKResetInterestCounterView(IntermediateAdminActionView):
    title = _("Reset AKs' interest counters")
    model = AK
    confirmation_message = _("Interest counter of the following AKs will be set to 0:")
    success_message = _("AKs' interest counters set back to 0.")

    def action(self, form):
        self.entities.update(interest_counter=0)


class PlanPublishView(IntermediateAdminActionView):
    title = _('Publish plan')
    model = Event
    confirmation_message = _('Publish the plan(s) of:')
    success_message = _('Plan published')

    def action(self, form):
        self.entities.update(plan_published_at=Now(), plan_hidden=False)


class PlanUnpublishView(IntermediateAdminActionView):
    title = _('Unpublish plan')
    model = Event
    confirmation_message = _('Unpublish the plan(s) of:')
    success_message = _('Plan unpublished')

    def action(self, form):
        self.entities.update(plan_published_at=None, plan_hidden=True)


class DefaultSlotEditorView(EventSlugMixin, IntermediateAdminView):
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

        for slot in default_slots_raw:
            start = parse_datetime(slot["start"]).astimezone(tz)
            end = parse_datetime(slot["end"]).astimezone(tz)

            if slot["id"] != '':
                id = int(slot["id"])
                if id not in previous_slot_ids:
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
                    previous_slot_ids.remove(id)
                    original_slot = DefaultSlot.objects.get(id=id)
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

        if created_count + updated_count + deleted_count > 0:
            messages.add_message(
                self.request,
                messages.SUCCESS,
                _("Updated {u} slot(s). created {c} new slot(s) and deleted {d} slot(s)")
                .format(u=str(updated_count), c=str(created_count), d=str(deleted_count))
            )
        return super().form_valid(form)


class RoomBatchCreationView(EventSlugMixin, IntermediateAdminView):
    form_class = RoomBatchCreationForm
    title = _("Import Rooms from CSV")

    def get_success_url(self):
        return reverse_lazy('admin:event_status', kwargs={'slug': self.event.slug})

    def form_valid(self, form):
        virtual_rooms_support = False
        created_count = 0

        rooms_raw_dict: csv.DictReader = form.cleaned_data["rooms"]

        if apps.is_installed("AKOnline") and "url" in rooms_raw_dict.fieldnames:
            virtual_rooms_support = True
            from AKOnline.models import VirtualRoom

        for raw_room in rooms_raw_dict:
            name = raw_room["name"]
            location = raw_room["location"] if "location" in rooms_raw_dict.fieldnames else ""
            capacity = raw_room["capacity"] if "capacity" in rooms_raw_dict.fieldnames else -1

            try:
                if virtual_rooms_support and raw_room["url"] != "":
                    VirtualRoom.objects.create(name=name,
                                               location=location,
                                               capacity=capacity,
                                               url=raw_room["url"],
                                               event=self.event)
                else:
                    Room.objects.create(name=name,
                                        location=location,
                                        capacity=capacity,
                                        event=self.event)
                created_count += 1
            except django.db.Error as e:
                messages.add_message(self.request, messages.WARNING,
                                     _("Could not import room {name}: {e}").format(name=name, e=str(e)))

        if created_count > 0:
            messages.add_message(self.request, messages.SUCCESS,
                                 _("Imported {count} room(s)").format(count=created_count))
        else:
            messages.add_message(self.request, messages.WARNING, _("No rooms imported"))
        return super().form_valid(form)
