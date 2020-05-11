from django.urls import include, path
from rest_framework.routers import DefaultRouter

from AKModel import views

api_router = DefaultRouter()
api_router.register('akowner', views.AKViewSet, basename='AKOwner')
api_router.register('akcategory', views.AKViewSet, basename='AKCategory')
api_router.register('aktrack', views.AKViewSet, basename='AKTrack')
api_router.register('ak', views.AKViewSet, basename='AK')
api_router.register('room', views.AKViewSet, basename='Room')
api_router.register('akslot', views.AKViewSet, basename='AKSlot')

app_name = 'model'

urlpatterns = [
    path(
        '<slug:event_slug>/',
        include([
            path('api/', include(api_router.urls), name='api'),
        ])
    ),
]
