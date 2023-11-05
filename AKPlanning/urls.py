"""
AKPlanning URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import debug_toolbar
from django.apps import apps
from django.contrib import admin
from django.urls import path, include, re_path

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^docs/', include('docs.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('registration.backends.simple.urls')),
    path('', include('AKModel.urls', namespace='model')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('__debug__/', include(debug_toolbar.urls)),
]

# Load URLs dynamically (only if components are active)
if apps.is_installed("AKSubmission"):
    urlpatterns.append(path('', include('AKSubmission.urls', namespace='submit')))
if apps.is_installed("AKDashboard"):
    urlpatterns.append(path('', include('AKDashboard.urls', namespace='dashboard')))
if apps.is_installed("AKPlan"):
    urlpatterns.append(path('', include('AKPlan.urls', namespace='plan')))
