# expenses/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GroupViewSet, ExpenseViewSet, SettlementViewSet, UserViewSet,
    register_view, login_view, logout_view, dashboard_view,
    create_group_view, group_detail_view, add_expense_view,
    settle_debt_view, delete_expense_view, export_expenses_csv,
    home_view, profile_view
)

router = DefaultRouter()
router.register(r'groups', GroupViewSet, basename='group')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'settlements', SettlementViewSet, basename='settlement')
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # Web Interface URLs
    path('', home_view, name='home'),  # Changed from dashboard_view
    path('dashboard/', dashboard_view, name='dashboard'),  # ADD this line
    path('profile/', profile_view, name='profile'),
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('create-group/', create_group_view, name='create_group'),
    path('group/<int:group_id>/', group_detail_view, name='group_detail'),
    path('group/<int:group_id>/add-expense/', add_expense_view, name='add_expense'),
    path('group/<int:group_id>/settle-debt/', settle_debt_view, name='settle_debt'),
    path('group/<int:group_id>/export/', export_expenses_csv, name='export_expenses'),
    path('delete-expense/<int:expense_id>/', delete_expense_view, name='delete_expense'),
    
    # API URLs
    path('api/', include(router.urls)),
]