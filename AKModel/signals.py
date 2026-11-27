# Signal receivers follow a fixed interface (e.g., a sender argument) that is hardly used here
# pylint: disable=unused-argument
"""
Signal receivers of AKModel (connected in :meth:`AKModel.apps.AkmodelConfig.ready`)
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event, StatusTrackingEntry
from AKModel.status_tracking import status_tracker

Progress = StatusTrackingEntry.Progress


@receiver(pre_save, sender=Event)
def remember_previous_activation_state(sender, instance: Event, raw=False, **kwargs):
    """
    Remember whether the event was active before saving to detect (de)activations in :func:`track_event_activation`
    """
    previous = None
    if not raw and instance.pk is not None:
        previous = Event.objects.filter(pk=instance.pk).values_list("active", flat=True).first()
    # Not a model field, just remembered on the instance until post_save
    setattr(instance, "_previous_active", previous)


@receiver(post_save, sender=Event)
def track_event_activation(sender, instance: Event, created: bool, raw=False, **kwargs):
    """
    Track the activation and deactivation of events (no matter where it happened, e.g., wizard or admin)

    Activating marks the step "Activate event" (configuration phase) as done,
    deactivating an active event marks the step "Deactivate event" (aftermath phase) as done.
    Nothing is recorded when loading fixtures (raw saves) or when saving without changing the state.
    """
    if raw:
        return
    previous = getattr(instance, "_previous_active", None)
    if instance.active and not previous:
        status_tracker.record(instance, "configuration", "activate", Progress.DONE,
                              detail=str(_("Event was activated")))
    elif not instance.active and previous:
        status_tracker.record(instance, "aftermath", "deactivate", Progress.DONE,
                              detail=str(_("Event was deactivated")))
