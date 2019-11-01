from django.urls import include, path

from AKPlan import views
from AKScheduling.urls import api_router

app_name = 'plan'

urlpatterns = [
    path(
        '<slug:event_slug>/plan/',
        include([
            path('', views.CurrentNextAKsView.as_view(), name='ak_plan'),
            path('timeline/', views.plan_beamer, name='ak_plan_timeline'),
            path('current_next/', views.CurrentNextAKsView.as_view(), name='ak_plan_current_next'),
            path('current_next/beamer/', views.CurrentNextAKsBeamerView.as_view(), name='ak_plan_current_next_beamer'),
            path('api/', include(api_router.urls)),

        ])
    ),

]
