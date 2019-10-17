from django.urls import path, include

from . import views

app_name = "submit"

urlpatterns = [
    path(
        '<slug:event_slug>/',
        include([
            path('submission/', views.SubmissionOverviewView.as_view(), name='submission_overview'),
        ])
    ),
]
