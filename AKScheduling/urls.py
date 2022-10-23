from django.urls import path

from AKScheduling.views import SchedulingAdminView, UnscheduledSlotsAdminView, TrackAdminView, \
    ConstraintViolationsAdminView, SpecialAttentionAKsAdminView, InterestEnteringAdminView, WishSlotCleanupView, \
    AvailabilityAutocreateView


def get_admin_urls_scheduling(admin_site):
    return [
        path('<slug:event_slug>/schedule/', admin_site.admin_view(SchedulingAdminView.as_view()),
             name="schedule"),
        path('<slug:event_slug>/unscheduled/', admin_site.admin_view(UnscheduledSlotsAdminView.as_view()),
             name="slots_unscheduled"),
        path('<slug:slug>/constraint-violations/', admin_site.admin_view(ConstraintViolationsAdminView.as_view()),
             name="constraint-violations"),
        path('<slug:slug>/special-attention/', admin_site.admin_view(SpecialAttentionAKsAdminView.as_view()),
             name="special-attention"),
        path('<slug:event_slug>/cleanup-wish-slots/', admin_site.admin_view(WishSlotCleanupView.as_view()),
             name="cleanup-wish-slots"),
        path('<slug:event_slug>/autocreate-availabilities/', admin_site.admin_view(AvailabilityAutocreateView.as_view()),
             name="autocreate-availabilities"),
        path('<slug:event_slug>/tracks/', admin_site.admin_view(TrackAdminView.as_view()),
             name="tracks_manage"),
        path('<slug:event_slug>/enter-interest/<int:pk>', admin_site.admin_view(InterestEnteringAdminView.as_view()),
             name="enter-interest"),
    ]
