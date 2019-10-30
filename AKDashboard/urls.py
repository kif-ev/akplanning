from django.conf.urls import url
from django.urls import path

from AKDashboard import views

app_name = "dashboard"

urlpatterns = [
    path('', views.TopLevelRedirectView.as_view(), name='top_level_redirect'),
    url(r'^index/$', views.Index.as_view(), name="index"),
]
