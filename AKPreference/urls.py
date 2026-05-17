from django.urls import include, path

from . import views

app_name = "poll"

urlpatterns = [
    path(
        '<slug:event_slug>/poll/',
        include(
            [
                path("old/", views.PreferencePollCreateView.as_view(), name="poll"),
                path("start/", views.PreferencePollStartView.as_view(), name="poll-start"),
                path("overview/", views.PreferencePollOverview.as_view(), name="poll-overview"),
                path("update/", views.ParticipantUpdateView.as_view(), name="participant-update"),
                path("delete/", views.DeleteInformationAndPreferencesView.as_view(), name="participant-delete"),
            ]
        ),
    ),
]
