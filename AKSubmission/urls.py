from django.urls import path, include

from . import views

app_name = "submit"

urlpatterns = [
    path(
        '<slug:event_slug>/submission/',
        include([
            path('', views.SubmissionOverviewView.as_view(), name='submission_overview'),
            path('ak/<int:pk>/', views.AKDetailView.as_view(), name='ak_detail'),
            path('ak/<int:pk>/history/', views.AKHistoryView.as_view(), name='ak_history'),
            path('ak/<int:pk>/edit/', views.AKEditView.as_view(), name='ak_edit'),
            path('ak/<int:pk>/interest/', views.AKInterestView.as_view(), name='inc_interest'),
            path('ak/<int:pk>/overview_interest/', views.AKOverviewInterestView.as_view(), name='overview_inc_interest'),
            path('ak/<int:pk>/add_slot/', views.AKSlotAddView.as_view(), name='akslot_add'),
            path('ak/<int:pk>/add_message/', views.AKAddOrgaMessageView.as_view(), name='akmessage_add'),
            path('akslot/<int:pk>/edit/', views.AKSlotEditView.as_view(), name='akslot_edit'),
            path('akslot/<int:pk>/delete/', views.AKSlotDeleteView.as_view(), name='akslot_delete'),
            path('aks/', views.AKOverviewView.as_view(), name='ak_list'),
            path('aks/category/<int:category_pk>/', views.AKListByCategoryView.as_view(), name='ak_list_by_category'),
            path('aks/tag/<int:tag_pk>/', views.AKListByTagView.as_view(), name='ak_list_by_tag'),
            path('aks/track/<int:track_pk>/', views.AKListByTrackView.as_view(), name='ak_list_by_track'),
            path('owner/', views.AKOwnerCreateView.as_view(), name='akowner_create'),
            path('new/', views.AKOwnerSelectDispatchView.as_view(), name='akowner_select'),
            path('owner/edit/', views.AKOwnerEditDispatchView.as_view(), name='akowner_edit_dispatch'),
            path('<slug:slug>/edit/', views.AKOwnerEditView.as_view(), name='akowner_edit'),
            path('<slug:owner_slug>/new/', views.AKSubmissionView.as_view(), name='submit_ak'),
            path('new_wish/', views.AKWishSubmissionView.as_view(), name='submit_ak_wish'),
            path('error/', views.SubmissionErrorNotConfiguredView.as_view(), name='error_not_configured'),
        ])
    ),
]
