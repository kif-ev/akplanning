from django.urls import include, path

from . import views

app_name = "poll"

urlpatterns = [
    path(
        '<slug:event_slug>/poll/',
        include(
            [
                path("start/", views.PreferencePollStartView.as_view(), name="start"),
                path("overview/", views.PreferencePollOverview.as_view(), name="overview"),
                path("enter/<int:category_pk>/", views.EnterPreferencesView.as_view(), name="preferences-enter"),
                path("update/", views.ParticipantUpdateView.as_view(), name="participant-update"),
                path("delete/", views.DeleteInformationAndPreferencesView.as_view(), name="participant-delete"),
            ]
        ),
    ),
]
