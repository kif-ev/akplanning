from itertools import zip_longest

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, DetailView, ListView, DeleteView, CreateView, FormView, UpdateView
from django_tex.shortcuts import render_to_pdf
from rest_framework import viewsets, permissions, mixins

from AKModel.forms import NewEventWizardStartForm, NewEventWizardSettingsForm, NewEventWizardPrepareImportForm, \
    NewEventWizardImportForm, NewEventWizardActivateForm
from AKModel.models import Event, AK, AKSlot, Room, AKTrack, AKCategory, AKOwner, AKOrgaMessage, AKRequirement
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


class AKSlotViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
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

        categories_with_aks, ak_wishes = context["event"].get_categories_with_aks(wishes_seperately=True)

        context["categories_with_aks"] = [(category.name, ak_list) for category, ak_list in categories_with_aks]
        context["categories_with_aks"].append((_("Wishes"), ak_wishes))

        return context


class AKMessageDeleteView(AdminViewMixin, DeleteView):
    model = Event
    template_name = "admin/AKModel/message_delete.html"

    def get_orga_messages_for_event(self, event):
        return AKOrgaMessage.objects.filter(ak__event=event)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ak_messages"] = self.get_orga_messages_for_event(self.get_object())
        return context

    def post(self, request, *args, **kwargs):
        self.get_orga_messages_for_event(self.get_object()).delete()
        messages.add_message(self.request, messages.SUCCESS, _("AK Orga Messages successfully deleted"))
        return HttpResponseRedirect(reverse_lazy('admin:event_status', kwargs={'slug': self.get_object().slug}))


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
        for import_type in ["import_categories", "import_requirements"]:
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


@staff_member_required
def export_slides(request, event_slug):
    template_name = 'admin/AKModel/export/slides.tex'

    event = get_object_or_404(Event, slug=event_slug)

    NEXT_AK_LIST_LENGTH = int(request.GET["num_next"]) if "num_next" in request.GET else 3
    RESULT_PRESENTATION_MODE = True if "presentation_mode" in request.GET else False
    SPACE_FOR_NOTES_IN_WISHES = request.GET["wish_notes"] == "True" if "wish_notes" in request.GET else False

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

    categories_with_aks, ak_wishes = event.get_categories_with_aks(wishes_seperately=True, filter=lambda
        ak: not RESULT_PRESENTATION_MODE or (ak.present or (ak.present is None and ak.category.present_by_default)))

    context = {
        'title': event.name,
        'categories_with_aks': [(category, build_ak_list_with_next_aks(ak_list)) for category, ak_list in
                                categories_with_aks],
        'subtitle': _("AKs"),
        "wishes": build_ak_list_with_next_aks(ak_wishes),
        "translations": translations,
        "result_presentation_mode": RESULT_PRESENTATION_MODE,
        "space_for_notes_in_wishes": SPACE_FOR_NOTES_IN_WISHES,
    }

    return render_to_pdf(request, template_name, context, filename='slides.pdf')
