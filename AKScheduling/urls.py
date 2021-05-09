from django.urls import path

from AKScheduling.views import SchedulingAdminView, UnscheduledSlotsAdminView, TrackAdminView, \
    ConstraintViolationsAdminView


def get_admin_urls_scheduling(admin_site):
    return [
        path('<slug:event_slug>/schedule/', admin_site.admin_view(SchedulingAdminView.as_view()),
             name="schedule"),
        path('<slug:event_slug>/unscheduled/', admin_site.admin_view(UnscheduledSlotsAdminView.as_view()),
             name="slots_unscheduled"),
        path('<slug:slug>/constraint-violations/', admin_site.admin_view(ConstraintViolationsAdminView.as_view()),
             name="constraint-violations"),
        path('<slug:event_slug>/tracks/', admin_site.admin_view(TrackAdminView.as_view()),
             name="tracks_manage"),
    ]
