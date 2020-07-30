from django.apps import apps
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from AKModel import views

api_router = DefaultRouter()
api_router.register('akowner', views.AKOwnerViewSet, basename='AKOwner')
api_router.register('akcategory', views.AKCategoryViewSet, basename='AKCategory')
api_router.register('aktrack', views.AKTrackViewSet, basename='AKTrack')
api_router.register('ak', views.AKViewSet, basename='AK')
api_router.register('room', views.RoomViewSet, basename='Room')
api_router.register('akslot', views.AKSlotViewSet, basename='AKSlot')


extra_paths = []
if apps.is_installed("AKScheduling"):
    from AKScheduling.api import ResourcesViewSet, RoomAvailabilitiesView, EventsView, EventsViewSet

    api_router.register('scheduling-resources', ResourcesViewSet, basename='scheduling-resources')
    api_router.register('scheduling-event', EventsViewSet, basename='scheduling-event')

    extra_paths = [
        path('api/scheduling-events/', EventsView.as_view(), name='scheduling-events'),
        path('api/scheduling-room-availabilities/', RoomAvailabilitiesView.as_view(), name='scheduling-room-availabilities'),
    ]


event_specific_paths = [
            path('api/', include(api_router.urls), name='api'),
        ]
event_specific_paths.extend(extra_paths)


app_name = 'model'


urlpatterns = [
    path(
        '<slug:event_slug>/',
        include(event_specific_paths)
    ),
    path('user/', views.UserView.as_view(), name="user"),
]
