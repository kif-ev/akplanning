from django.urls import path, include

from AKModel import views

app_name = 'model'

urlpatterns = [
    path(
        '<slug:event_slug>/',
        include([
            path('import/rooms/csv/', views.ImportRoomsCSVView.as_view(), name="import_room_csv"),
        ])
    ),
]
