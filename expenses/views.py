# expenses/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from .models import Group, Expense, ExpenseSplit, Settlement
from .utils import simplify_debts, calculate_group_statistics
from django.http import JsonResponse
from django.db.models import Sum
from django.views.decorators.http import require_POST
import csv
from django.http import HttpResponse
from .serializers import (
    GroupSerializer, ExpenseSerializer, 
    SettlementSerializer, UserSerializer
)

class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Only return groups where user is a member
        return Group.objects.filter(members=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['get'])
    def balances(self, request, pk=None):
        """
        Calculate who owes whom in this group
        """
        group = self.get_object()
        balances = {}
        
        # Get all unsettled splits for this group
        splits = ExpenseSplit.objects.filter(
            expense__group=group,
            is_settled=False
        ).select_related('user', 'expense__paid_by')
        
        # Calculate net balance for each user
        for split in splits:
            user = split.user.username
            paid_by = split.expense.paid_by.username
            
            if user not in balances:
                balances[user] = {}
            
            if paid_by not in balances[user]:
                balances[user][paid_by] = 0
            
            # This user owes money to paid_by
            if user != paid_by:
                balances[user][paid_by] += float(split.amount_owed)
        
        return Response(balances)

class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Only return expenses from groups user is member of
        return Expense.objects.filter(group__members=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(paid_by=self.request.user)

class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Settlement.objects.filter(
            Q(paid_by=self.request.user) | Q(paid_to=self.request.user)
        )
    
    def perform_create(self, serializer):
        settlement = serializer.save(paid_by=self.request.user)
        
        # Mark relevant splits as settled
        ExpenseSplit.objects.filter(
            expense__group=settlement.group,
            user=settlement.paid_by,
            expense__paid_by=settlement.paid_to,
            is_settled=False
        ).update(is_settled=True)

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

# expenses/views.py - ADD these functions at the bottom

# Authentication Views
def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        
        if password1 != password2:
            messages.error(request, 'Passwords do not match!')
            return redirect('register')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists!')
            return redirect('register')
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name
        )
        messages.success(request, 'Registration successful! Please login.')
        return redirect('login')
    
    return render(request, 'expenses/register.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password!')
    
    return render(request, 'expenses/login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('login')

@login_required
def dashboard_view(request):
    groups = Group.objects.filter(members=request.user).order_by('-created_at')
    
    context = {
        'groups': groups,
    }
    return render(request, 'expenses/dashboard.html', context)

@login_required
def create_group_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        member_usernames = request.POST.get('member_usernames', '')
        
        group = Group.objects.create(
            name=name,
            description=description,
            created_by=request.user
        )
        
        # Add creator as member
        group.members.add(request.user)
        
        # Add members by username
        if member_usernames:
            # Split by comma and clean whitespace
            usernames = [username.strip() for username in member_usernames.split(',')]
            
            not_found = []
            added_count = 0
            
            for username in usernames:
                if username:  # Skip empty strings
                    try:
                        user = User.objects.get(username=username)
                        if user != request.user:  # Don't add creator again
                            group.members.add(user)
                            added_count += 1
                    except User.DoesNotExist:
                        not_found.append(username)
            
            # Success message
            if added_count > 0:
                messages.success(request, f'Group "{name}" created! Added {added_count} member(s).')
            else:
                messages.success(request, f'Group "{name}" created successfully!')
            
            # Warning for not found users
            if not_found:
                messages.warning(request, f'Could not find these users: {", ".join(not_found)}. Check spelling and try adding them later.')
        else:
            messages.success(request, f'Group "{name}" created successfully! You can add members from the group page.')
        
        return redirect('dashboard')
    
    return redirect('dashboard')

@login_required
def group_detail_view(request, group_id):
    group = get_object_or_404(Group, id=group_id, members=request.user)
    expenses = group.expenses.all().order_by('-date')
    
    # Calculate balances
    balances = {}
    splits = ExpenseSplit.objects.filter(
        expense__group=group,
        is_settled=False
    ).select_related('user', 'expense__paid_by')
    
    for split in splits:
        user = split.user.username
        paid_by = split.expense.paid_by.username
        
        if user not in balances:
            balances[user] = {}
        
        if paid_by not in balances[user]:
            balances[user][paid_by] = 0
        
        if user != paid_by:
            balances[user][paid_by] += float(split.amount_owed)
    
    context = {
        'group': group,
        'expenses': expenses,
        'balances': balances,
    }
    return render(request, 'expenses/group_detail.html', context)

@login_required
def add_expense_view(request, group_id):
    group = get_object_or_404(Group, id=group_id, members=request.user)
    
    if request.method == 'POST':
        description = request.POST.get('description')
        amount = request.POST.get('amount')
        expense_date = request.POST.get('date')
        split_member_ids = request.POST.getlist('split_members')
        
        if not split_member_ids:
            messages.error(request, 'Please select at least one member to split with!')
            return redirect('add_expense', group_id=group_id)
        
        # Create expense
        expense = Expense.objects.create(
            group=group,
            description=description,
            amount=amount,
            paid_by=request.user,
            date=expense_date
        )
        
        # Create splits
        split_amount = float(amount) / len(split_member_ids)
        for member_id in split_member_ids:
            ExpenseSplit.objects.create(
                expense=expense,
                user_id=member_id,
                amount_owed=split_amount
            )
        
        messages.success(request, f'Expense "{description}" added successfully!')
        return redirect('group_detail', group_id=group_id)
    
    context = {
        'group': group,
        'today': date.today().isoformat(),
    }
    return render(request, 'expenses/add_expense.html', context)

@login_required
def settle_debt_view(request, group_id):
    group = get_object_or_404(Group, id=group_id, members=request.user)
    
    if request.method == 'POST':
        paid_to_id = request.POST.get('paid_to')
        amount = request.POST.get('amount')
        
        paid_to = get_object_or_404(User, id=paid_to_id)
        
        # Create settlement record
        settlement = Settlement.objects.create(
            group=group,
            paid_by=request.user,
            paid_to=paid_to,
            amount=amount
        )
        
        # Mark relevant splits as settled
        # Find all unsettled splits where current user owes to paid_to
        splits_to_settle = ExpenseSplit.objects.filter(
            expense__group=group,
            user=request.user,
            expense__paid_by=paid_to,
            is_settled=False
        ).order_by('expense__date')
        
        remaining_amount = float(amount)
        
        for split in splits_to_settle:
            if remaining_amount <= 0:
                break
            
            split_amount = float(split.amount_owed)
            
            if remaining_amount >= split_amount:
                # Fully settle this split
                split.is_settled = True
                split.save()
                remaining_amount -= split_amount
            else:
                # Partially settle (for future enhancement)
                # For now, we'll just mark as settled if payment covers it
                break
        
        messages.success(request, f'Payment of ${amount} to {paid_to.username} recorded successfully!')
        return redirect('group_detail', group_id=group_id)
    
    context = {
        'group': group,
    }
    return render(request, 'expenses/settle_debt.html', context)

@login_required
@require_POST
def delete_expense_view(request, expense_id):
    try:
        expense = get_object_or_404(Expense, id=expense_id)
        group = expense.group
        
        # Check if user is member of the group
        if not group.members.filter(id=request.user.id).exists():
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
        
        # Check if user created the expense or is group creator
        if expense.paid_by != request.user and group.created_by != request.user:
            return JsonResponse({'success': False, 'error': 'Only expense creator or group admin can delete'}, status=403)
        
        expense.delete()
        return JsonResponse({'success': True})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def group_detail_view(request, group_id):
    group = get_object_or_404(Group, id=group_id, members=request.user)
    expenses = group.expenses.all().order_by('-date')
    
    # Calculate balances
    balances = {}
    splits = ExpenseSplit.objects.filter(
        expense__group=group,
        is_settled=False
    ).select_related('user', 'expense__paid_by')
    
    for split in splits:
        user = split.user.username
        paid_by = split.expense.paid_by.username
        
        if user not in balances:
            balances[user] = {}
        
        if paid_by not in balances[user]:
            balances[user][paid_by] = 0
        
        if user != paid_by:
            balances[user][paid_by] += float(split.amount_owed)
    
    # Get simplified balances
    simplified_balances = simplify_debts(balances)
    
    # Get statistics
    statistics = calculate_group_statistics(group)
    
    context = {
        'group': group,
        'expenses': expenses,
        'balances': balances,
        'simplified_balances': simplified_balances,
        'statistics': statistics,
    }
    return render(request, 'expenses/group_detail.html', context)

@login_required
def export_expenses_csv(request, group_id):
    group = get_object_or_404(Group, id=group_id, members=request.user)
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{group.name}_expenses.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Description', 'Amount', 'Paid By', 'Split Among'])
    
    for expense in group.expenses.all().order_by('-date'):
        split_members = ', '.join([split.user.username for split in expense.splits.all()])
        writer.writerow([
            expense.date,
            expense.description,
            expense.amount,
            expense.paid_by.username,
            split_members
        ])
    
    return response

def home_view(request):
    """Landing page view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'expenses/home.html')

# expenses/views.py - ADD these functions at the bottom

def custom_404(request, exception):
    """Custom 404 error handler"""
    return render(request, 'expenses/404.html', status=404)

def custom_500(request):
    """Custom 500 error handler"""
    return render(request, 'expenses/500.html', status=500)

@login_required
def profile_view(request):
    if request.method == 'POST':
        # Update user profile
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.email = request.POST.get('email', '')
        request.user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    
    # Calculate statistics
    groups_count = Group.objects.filter(members=request.user).count()
    expenses_count = Expense.objects.filter(paid_by=request.user).count()
    total_paid = Expense.objects.filter(paid_by=request.user).aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    context = {
        'groups_count': groups_count,
        'expenses_count': expenses_count,
        'total_paid': total_paid,
    }
    return render(request, 'expenses/profile.html', context)

# expenses/views.py - ADD at the bottom

@login_required
def add_members_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    
    # Check if user is member of the group
    if not group.members.filter(id=request.user.id).exists():
        messages.error(request, 'You must be a member of this group.')
        return redirect('dashboard')
    
    # Only group creator can add members
    if group.created_by != request.user:
        messages.error(request, 'Only the group creator can add members.')
        return redirect('group_detail', group_id=group_id)
    
    if request.method == 'POST':
        member_usernames = request.POST.get('member_usernames', '')
        
        if member_usernames:
            usernames = [username.strip() for username in member_usernames.split(',')]
            
            added = []
            already_member = []
            not_found = []
            
            for username in usernames:
                if username:
                    try:
                        user = User.objects.get(username=username)
                        if user in group.members.all():
                            already_member.append(username)
                        else:
                            group.members.add(user)
                            added.append(username)
                    except User.DoesNotExist:
                        not_found.append(username)
            
            # Success messages
            if added:
                messages.success(request, f'Successfully added: {", ".join(added)}')
            if already_member:
                messages.info(request, f'Already members: {", ".join(already_member)}')
            if not_found:
                messages.warning(request, f'Users not found: {", ".join(not_found)}. Please check the usernames.')
            
            return redirect('group_detail', group_id=group_id)
    
    context = {'group': group}
    return render(request, 'expenses/add_members.html', context)