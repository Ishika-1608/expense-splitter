# expense_project/urls.py - REPLACE entire file

from django.contrib import admin
from django.urls import path, include
from django.conf import settings

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('expenses.urls')),
    path('api-auth/', include('rest_framework.urls')),
]

# Custom error handlers
handler404 = 'expenses.views.custom_404'
handler500 = 'expenses.views.custom_500'