from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView
from rest_framework import viewsets, mixins, serializers, permissions

from AKModel.availability.models import Availability
from AKModel.models import Room, AKSlot, ConstraintViolation, DefaultSlot
from AKModel.metaviews.admin import EventSlugMixin


class ResourceSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for Rooms to produce format required for fullcalendar resources
    """
    class Meta:
        model = Room
        fields = ['id', 'title', 'details']

    title = serializers.SerializerMethodField('transform_title')

    @staticmethod
    def transform_title(obj):
        """
        Adapt title, add capacity information if room has a restriction (capacity is not -1)
        """
        if obj.capacity > 0:
            return f"{obj.title} [{obj.capacity}]"
        return obj.title


class ResourcesViewSet(EventSlugMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    API View: Rooms (resources to schedule for in fullcalendar)

    Read-only, adaption to fullcalendar format through :class:`ResourceSerializer`
    """
    permission_classes = (permissions.DjangoModelPermissions,)
    serializer_class = ResourceSerializer

    def get_queryset(self):
        return Room.objects.filter(event=self.event).order_by('location', 'name')


class EventsView(LoginRequiredMixin, EventSlugMixin, ListView):
    """
    API View: Slots (events to schedule in fullcalendar)

    Read-only, JSON formatted response is created manually since it requires a bunch of "custom" fields that have
    different names compared to the normal model or are not present at all and need to be computed to create the
    required format for fullcalendar.
    """
    model = AKSlot

    def get_queryset(self):
        return super().get_queryset().select_related('ak').filter(
            event=self.event, room__isnull=False, start__isnull=False
        )

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(
            [{
                "slotID": slot.pk,
                "title": f'{slot.ak.short_name}:\n{slot.ak.owners_list}',
                "description": slot.ak.details,
                "resourceId": slot.room.id,
                "start": timezone.localtime(slot.start, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "end": timezone.localtime(slot.end, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "backgroundColor": slot.ak.category.color,
                "borderColor":
                    "#2c3e50" if slot.fixed
                    else '#e74c3c' if slot.constraintviolation_set.count() > 0
                    else slot.ak.category.color,
                "constraint": 'roomAvailable',
                "editable": not slot.fixed,
                'url': str(reverse('admin:AKModel_akslot_change', args=[slot.pk])),
            } for slot in context["object_list"]],
            safe=False,
            **response_kwargs
        )


class RoomAvailabilitiesView(LoginRequiredMixin, EventSlugMixin, ListView):
    """
    API view: Availabilities of rooms

    Read-only, JSON formatted response is created manually since it requires a bunch of "custom" fields that have
    different names compared to the normal model or are not present at all and need to be computed to create the
    required format for fullcalendar.
    """
    model = Availability
    context_object_name = "availabilities"

    def get_queryset(self):
        return super().get_queryset().filter(event=self.event, room__isnull=False)

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(
            [{
                "title": "",
                "resourceId": a.room.id,
                "start": timezone.localtime(a.start, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "end": timezone.localtime(a.end, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "display": 'background',
                "groupId": 'roomAvailable',
            } for a in context["availabilities"]],
            safe=False,
            **response_kwargs
        )


class DefaultSlotsView(LoginRequiredMixin, EventSlugMixin, ListView):
    """
    API view: default slots

    Read-only, JSON formatted response is created manually since it requires a bunch of "custom" fields that have
    different names compared to the normal model or are not present at all and need to be computed to create the
    required format for fullcalendar.
    """
    model = DefaultSlot
    context_object_name = "default_slots"

    def get_queryset(self):
        return super().get_queryset().filter(event=self.event)

    def render_to_response(self, context, **response_kwargs):
        all_room_ids = [r.pk for r in self.event.room_set.all()]
        return JsonResponse(
            [{
                "title": "",
                "resourceIds": all_room_ids,
                "start": timezone.localtime(a.start, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "end": timezone.localtime(a.end, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "display": 'background',
                "groupId": 'defaultSlot',
                "backgroundColor": '#69b6d4'
            } for a in context["default_slots"]],
            safe=False,
            **response_kwargs
        )


class EventSerializer(serializers.ModelSerializer):
    """
    REST framework serializer to adapt between AKSlot model and the event format of fullcalendar
    """
    class Meta:
        model = AKSlot
        fields = ['id', 'start', 'end', 'roomId']

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    roomId = serializers.IntegerField(source='room.pk')

    def update(self, instance, validated_data):
        # Ignore timezone of input (treat it as timezone-less) and set the event timezone
        # By working like this, the client does not need to know about timezones, since every timestamp it deals with
        # has the timezone offsets already applied
        start = timezone.make_aware(timezone.make_naive(validated_data.get('start')), instance.event.timezone)
        end = timezone.make_aware(timezone.make_naive(validated_data.get('end')), instance.event.timezone)
        instance.start = start
        # Also, adapt from start & end format of fullcalendar to our start & duration model
        diff = end - start
        instance.duration = round(diff.days * 24 + (diff.seconds / 3600), 2)

        # Updated room if needed (pk changed -- otherwise, no need for an additional database lookup)
        new_room_id = validated_data.get('room')["pk"]
        if instance.room is None or instance.room.pk != new_room_id:
            instance.room = get_object_or_404(Room, pk=new_room_id)

        instance.save()
        return instance


class EventsViewSet(EventSlugMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    API view: Update scheduling of a slot (event in fullcalendar format)

    Write-only (will however reply with written values to PUT request)
    """
    permission_classes = (permissions.DjangoModelPermissions,)
    serializer_class = EventSerializer

    def get_object(self):
        return get_object_or_404(AKSlot, pk=self.kwargs["pk"])

    def get_queryset(self):
        return AKSlot.objects.filter(event=self.event)


class ConstraintViolationSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for constraint violations
    """
    class Meta:
        model = ConstraintViolation
        fields = ['pk', 'type_display', 'aks', 'ak_slots', 'ak_owner', 'room', 'requirement', 'category', 'comment',
                  'timestamp_display', 'manually_resolved', 'level_display', 'details', 'edit_url']


class ConstraintViolationsViewSet(EventSlugMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    API View: Constraint Violations of an event

    Read-only, fields and model selected in :class:`ConstraintViolationSerializer`
    """
    permission_classes = (permissions.DjangoModelPermissions,)
    serializer_class = ConstraintViolationSerializer

    def get_queryset(self):
        # Optimize query to reduce database load
        return (ConstraintViolation.objects.select_related('event', 'room')
                .prefetch_related('aks', 'ak_slots', 'ak_owner', 'requirement', 'category')
                .filter(event=self.event).order_by('manually_resolved', '-type', '-timestamp'))
