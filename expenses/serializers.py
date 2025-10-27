# expenses/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Group, Expense, ExpenseSplit, Settlement

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class GroupSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    members = UserSerializer(many=True, read_only=True)
    member_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'created_by', 'members', 'member_ids', 'created_at']
    
    def create(self, validated_data):
        member_ids = validated_data.pop('member_ids', [])
        group = Group.objects.create(**validated_data)
        
        # Add creator as member
        group.members.add(validated_data['created_by'])
        
        # Add other members
        if member_ids:
            group.members.add(*member_ids)
        
        return group

class ExpenseSplitSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = ExpenseSplit
        fields = ['id', 'user', 'amount_owed', 'is_settled']

class ExpenseSerializer(serializers.ModelSerializer):
    paid_by = UserSerializer(read_only=True)
    splits = ExpenseSplitSerializer(many=True, read_only=True)
    split_members = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True
    )
    
    class Meta:
        model = Expense
        fields = ['id', 'group', 'description', 'amount', 'paid_by', 'date', 'created_at', 'splits', 'split_members']
    
    def create(self, validated_data):
        split_members = validated_data.pop('split_members')
        expense = Expense.objects.create(**validated_data)
        
        # Calculate split amount
        split_amount = expense.amount / len(split_members)
        
        # Create splits for each member
        for user_id in split_members:
            ExpenseSplit.objects.create(
                expense=expense,
                user_id=user_id,
                amount_owed=split_amount
            )
        
        return expense

class SettlementSerializer(serializers.ModelSerializer):
    paid_by = UserSerializer(read_only=True)
    paid_to = UserSerializer(read_only=True)
    
    class Meta:
        model = Settlement
        fields = ['id', 'group', 'paid_by', 'paid_to', 'amount', 'settled_at']