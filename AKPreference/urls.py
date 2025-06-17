from django.urls import include, path

from . import views

app_name = "poll"

urlpatterns = [
    path(
        "<slug:event_slug>/poll/",
        include(
            [
                path("", views.PreferencePollCreateView.as_view(), name="poll"),
            ]
        ),
    ),
]
