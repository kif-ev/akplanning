from django.urls import path

from AKDashboard import views

app_name = "dashboard"

urlpatterns = [
    path('', views.DashboardView.as_view(), name="dashboard"),
]
