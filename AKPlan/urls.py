from django.urls import path, include
from . import views

app_name = "plan"

urlpatterns = [
    path(
        '<slug:event_slug>/plan/',
        include([
            path('', views.PlanIndexView.as_view(), name='plan_overview'),
            path('wall/', views.PlanScreenView.as_view(), name='plan_wall'),
        ])
    ),
]
