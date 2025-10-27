# expenses/utils.py

from decimal import Decimal
from collections import defaultdict

def simplify_debts(balances):
    """
    Simplify debts to minimize number of transactions.
    Uses greedy algorithm to match biggest debtor with biggest creditor.
    """
    # Create net balance for each person
    net_balance = defaultdict(Decimal)
    
    for debtor, creditors in balances.items():
        for creditor, amount in creditors.items():
            net_balance[debtor] -= Decimal(str(amount))
            net_balance[creditor] += Decimal(str(amount))
    
    # Separate debtors and creditors
    debtors = [(person, -amount) for person, amount in net_balance.items() if amount < 0]
    creditors = [(person, amount) for person, amount in net_balance.items() if amount > 0]
    
    # Sort in descending order
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)
    
    simplified = []
    i, j = 0, 0
    
    while i < len(debtors) and j < len(creditors):
        debtor, debt_amount = debtors[i]
        creditor, credit_amount = creditors[j]
        
        # Take minimum of debt and credit
        settle_amount = min(debt_amount, credit_amount)
        
        if settle_amount > 0:
            simplified.append({
                'from': debtor,
                'to': creditor,
                'amount': float(settle_amount)
            })
        
        # Update amounts
        debtors[i] = (debtor, debt_amount - settle_amount)
        creditors[j] = (creditor, credit_amount - settle_amount)
        
        # Move to next if current is settled
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    
    return simplified

def calculate_group_statistics(group):
    """
    Calculate statistics for a group.
    """
    from .models import Expense, ExpenseSplit
    from django.db.models import Sum
    
    expenses = Expense.objects.filter(group=group)
    
    total_spent = expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    # Per person spending
    member_stats = {}
    for member in group.members.all():
        paid = expenses.filter(paid_by=member).aggregate(total=Sum('amount'))['total'] or 0
        owed = ExpenseSplit.objects.filter(
            expense__group=group,
            user=member,
            is_settled=False
        ).aggregate(total=Sum('amount_owed'))['total'] or 0
        
        member_stats[member.username] = {
            'paid': float(paid),
            'owes': float(owed),
            'balance': float(paid) - float(owed)
        }
    
    return {
        'total_spent': float(total_spent),
        'expense_count': expenses.count(),
        'member_stats': member_stats
    }