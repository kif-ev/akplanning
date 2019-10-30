from django.urls import include, path

from AKPlan import views

app_name = 'plan'

urlpatterns = [
    path(
        '<slug:event_slug>/plan/',
        include([
            path('', views.PlanView.as_view(), name='ak_plan')
        ])
    ),

]
