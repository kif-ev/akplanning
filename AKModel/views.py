from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from django.views.generic import TemplateView, DetailView, ListView, DeleteView
from rest_framework import viewsets, permissions, mixins

from AKModel.models import Event, AK, AKSlot, Room, AKTrack, AKCategory, AKOwner, AKOrgaMessage
from AKModel.serializers import AKSerializer, AKSlotSerializer, RoomSerializer, AKTrackSerializer, AKCategorySerializer, \
    AKOwnerSerializer


class EventSlugMixin:
    """
    Mixin to handle views with event slugs
    """
    event = None

    def _load_event(self):
        # Find event based on event slug
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

    def initial(self, request, *args, **kwargs):
        if self.event is None:
            self._load_event()
        super().initial(request, *args, **kwargs)

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


class AKTrackViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKTrackSerializer

    def get_queryset(self):
        return AKTrack.objects.filter(event=self.event)


class AKViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
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


class AKWikiExportView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    template_name = "admin/AKModel/wiki_export.html"
    model = AK
    context_object_name = "AKs"
    title = _("AK Wiki Export")

    def get_queryset(self):
        return super().get_queryset().order_by("category")


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
