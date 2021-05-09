from django.urls import path

from AKScheduling.views import SchedulingAdminView, UnscheduledSlotsAdminView, TrackAdminView


def get_admin_urls_slot(admin_site):
    return [
        path('<slug:event_slug>/schedule/', admin_site.admin_view(SchedulingAdminView.as_view()),
             name="schedule"),
        path('<slug:event_slug>/unscheduled/', admin_site.admin_view(UnscheduledSlotsAdminView.as_view()),
             name="slots_unscheduled"),
    ]


def get_admin_urls_track(admin_site):
    return [
        path('<slug:event_slug>/manage/', admin_site.admin_view(TrackAdminView.as_view()),
             name="tracks_manage"),
    ]
