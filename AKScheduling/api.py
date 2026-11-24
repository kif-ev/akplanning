from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response

from AKModel.availability.models import Availability
from AKModel.metaviews.admin import EventSlugMixin
from AKModel.models import AKSlot, ConstraintViolation, DefaultSlot, Room


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
        return super().get_queryset().select_related('ak', 'ak__track', 'ak__category').prefetch_related(
                # Availabilities are needed for the details of the AKs,
                # load them together with their event (needed for the timezone when displaying them)
                Prefetch('ak__availabilities', queryset=Availability.objects.select_related('event')),
        ).filter(
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
                        else '#e74c3c' if slot.constraintviolation_set.filter(manually_resolved=False).count() > 0
                        else slot.ak.category.color,
                    "constraint": 'roomAvailable',
                    "editable": not slot.fixed,
                    # Information needed to show the slot in the list of unscheduled slots when unscheduling it
                    # (do not use "duration" here, fullcalendar treats that as property of recurring events and
                    # would hence not make it available as extendedProp)
                    "shortName": slot.ak.short_name,
                    "ownersList": slot.ak.owners_list,
                    "slotDuration": float(slot.duration),
                    "trackId": slot.ak.track_id,
                    "trackName": str(slot.ak.track) if slot.ak.track else "",
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

    # Colors for default slots, same as in the default slot editor
    COLOR_CATEGORY_WITHOUT_COLOR = '#158cba'
    COLOR_NO_CATEGORIES = '#8c8c8c'

    def get_queryset(self):
        return super().get_queryset().filter(event=self.event).prefetch_related('primary_categories')

    @classmethod
    def category_colors(cls, default_slot):
        """
        Get the colors of the primary categories of the given default slot (without duplicates)

        Slots with multiple colors are displayed with diagonal stripes in these colors in the scheduler.

        :return: list of CSS colors (contains a neutral color if the slot has no primary categories)
        """
        colors = [c.css_color or cls.COLOR_CATEGORY_WITHOUT_COLOR for c in default_slot.primary_categories.all()]
        return list(dict.fromkeys(colors)) or [cls.COLOR_NO_CATEGORIES]

    def render_to_response(self, context, **response_kwargs):
        all_room_ids = [r.pk for r in self.event.room_set.all()]
        events = []
        for a in context["default_slots"]:
            colors = self.category_colors(a)
            events.append({
                "title": "",
                "resourceIds": all_room_ids,
                "start": timezone.localtime(a.start, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "end": timezone.localtime(a.end, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "display": 'background',
                "groupId": 'defaultSlot',
                "backgroundColor": colors[0],
                "categoryColors": colors,
            })
        return JsonResponse(events, safe=False, **response_kwargs)


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


class ChangePermissionForPost(permissions.DjangoModelPermissions):
    """
    Model permissions requiring change permission for POST requests

    Needed for actions that modify existing objects via POST (instead of creating new objects)
    """
    perms_map = {**permissions.DjangoModelPermissions.perms_map,
                 'POST': ['%(app_label)s.change_%(model_name)s']}


class EventsViewSet(EventSlugMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    API view: Update scheduling of a slot (event in fullcalendar format)

    Write-only (will however reply with written values to PUT request).
    Slots can be removed from the schedule using the ``unschedule`` action.
    """
    permission_classes = (permissions.DjangoModelPermissions,)
    serializer_class = EventSerializer

    def get_object(self):
        return get_object_or_404(AKSlot, pk=self.kwargs["pk"])

    def get_queryset(self):
        return AKSlot.objects.filter(event=self.event)

    def list(self, request, *args, **kwargs):
        raise MethodNotAllowed('GET')

    @action(detail=True, methods=['post'], permission_classes=[ChangePermissionForPost])
    def unschedule(self, request, *args, **kwargs):
        """
        Remove a slot from the schedule (i.e., reset its start and room)

        Fixed slots cannot be unscheduled.
        """
        slot = get_object_or_404(AKSlot, pk=self.kwargs["pk"], event=self.event)
        if slot.fixed:
            return Response({'detail': 'Scheduling of this slot is fixed'}, status=status.HTTP_400_BAD_REQUEST)
        slot.start = None
        slot.room = None
        slot.save()
        return Response({'id': slot.pk})


class ConstraintViolationSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for constraint violations
    """

    class Meta:
        model = ConstraintViolation
        fields = ['pk', 'type_display', 'aks', 'ak_slots', 'ak_owner', 'room', 'requirement', 'category', 'comment',
                  'timestamp_display', 'manually_resolved', 'level_display', 'details', 'edit_url',
                  'resolution_reason', 'resolved_by_display', 'resolution_display']

    resolved_by_display = serializers.SerializerMethodField()
    resolution_display = serializers.SerializerMethodField()

    @staticmethod
    def get_resolved_by_display(obj):
        """
        Name of the user who marked the violation as resolved (empty if unknown or not resolved)
        """
        if obj.resolved_by is None:
            return ""
        return obj.resolved_by.get_full_name() or obj.resolved_by.get_username()

    def get_resolution_display(self, obj):
        """
        Human-readable information about the manual resolution of the violation, i.e., who resolved it and why
        (empty if the violation is not manually resolved)
        """
        if not obj.manually_resolved:
            return ""
        resolved_by = self.get_resolved_by_display(obj)
        text = _("Resolved by %(user)s") % {'user': resolved_by} if resolved_by else str(_("Manually Resolved"))
        if obj.resolution_reason:
            text = f"{text}: {obj.resolution_reason}"
        return text


class ConstraintViolationsViewSet(EventSlugMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    API View: Constraint Violations of an event

    Read-only, fields and model selected in :class:`ConstraintViolationSerializer`
    """
    permission_classes = (permissions.DjangoModelPermissions,)
    serializer_class = ConstraintViolationSerializer

    def get_queryset(self):
        # Optimize query to reduce database load
        return (ConstraintViolation.objects.select_related('event', 'room', 'resolved_by')
                .prefetch_related('aks', 'ak_slots', 'ak_owner', 'requirement', 'category')
                .filter(event=self.event).order_by('manually_resolved', '-type', '-timestamp'))
