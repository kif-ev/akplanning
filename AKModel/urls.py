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

app_name = 'model'

urlpatterns = [
    path(
        '<slug:event_slug>/',
        include([
            path('api/', include(api_router.urls), name='api'),
        ])
    ),
    path('user/', views.UserView.as_view(), name="user"),
]
