from django.conf.urls import url
from django.urls import path

from AKDashboard import views

app_name = "dashboard"

urlpatterns = [
    path('', views.TopLevelRedirectView.as_view(), name='top_level_redirect'),
    url(r'^dashboard/$', views.DashboardView.as_view(), name="dashboard"),
]
