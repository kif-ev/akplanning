from django.urls import include, path

from AKPlan import views
from AKScheduling.urls import api_router

app_name = 'plan'

urlpatterns = [
    path(
        '<slug:event_slug>/plan/',
        include([
            path('', views.plan_beamer, name='ak_plan'),
            path('api/', include(api_router.urls)),

        ])
    ),

]
