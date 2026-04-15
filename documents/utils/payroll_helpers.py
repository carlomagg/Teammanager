"""
Utility functions for payroll processing.
Includes role hierarchy, password management, and net amount calculations.
"""
from decimal import Decimal
from django.contrib.auth.hashers import make_password, check_password


def get_role_hierarchy():
    """
    Return role hierarchy for payroll approval order.
    Lower numbers = lower in hierarchy, higher numbers = higher authority.
    
    Returns:
        dict: Role name to hierarchy level mapping
    """
    return {
        'HR': 1,
        'Admin': 1,
        'Accountant': 2,
        'Finance Manager': 3,
        'MD': 4,
        'CEO': 5,
        'Board Chair': 6
    }


def get_user_highest_role_level(user):
    """
    Get user's highest role level in the hierarchy.
    
    Args:
        user: CustomUser instance
        
    Returns:
        int: Highest role level (0 if no payroll-related roles)
    """
    hierarchy = get_role_hierarchy()
    user_roles = user.roles.all()
    levels = [hierarchy.get(role.name, 0) for role in user_roles]
    return max(levels) if levels else 0


def user_can_approve_payroll(user):
    """
    Check if user has any role that can approve payroll.
    
    Args:
        user: CustomUser instance
        
    Returns:
        bool: True if user can approve payroll
    """
    return get_user_highest_role_level(user) > 0


def user_can_pay_payroll(user):
    """
    Check if user has authority to execute payment (Finance Manager or higher).
    
    Args:
        user: CustomUser instance
        
    Returns:
        bool: True if user can execute payment
    """
    hierarchy = get_role_hierarchy()
    user_roles = user.roles.all()
    
    # Finance Manager level (3) or higher can pay
    for role in user_roles:
        if hierarchy.get(role.name, 0) >= 3:
            return True
    return False


def get_user_role_name(user):
    """
    Get user's highest payroll-related role name.
    
    Args:
        user: CustomUser instance
        
    Returns:
        str: Role name or 'User' if no payroll roles
    """
    hierarchy = get_role_hierarchy()
    user_roles = user.roles.all()
    
    highest_level = 0
    highest_role = 'User'
    
    for role in user_roles:
        level = hierarchy.get(role.name, 0)
        if level > highest_level:
            highest_level = level
            highest_role = role.name
    
    return highest_role


def calculate_net_amount(gross_amount, column_values, custom_columns):
    """
    Calculate net amount based on gross and custom column operations.
    
    Args:
        gross_amount (Decimal): Gross salary amount
        column_values (dict): Column name to value mapping
        custom_columns (QuerySet): PayrollCustomColumn queryset
        
    Returns:
        Decimal: Calculated net amount
        
    Example:
        gross = Decimal('100000')
        values = {'Tax': 10000, 'Pension': 8000, 'Bonus': 5000}
        columns = PayrollCustomColumn.objects.filter(payroll=payroll)
        net = calculate_net_amount(gross, values, columns)
        # net = 100000 - 10000 - 8000 + 5000 = 87000
    """
    net = Decimal(str(gross_amount))
    
    for column in custom_columns.order_by('order'):
        value = Decimal(str(column_values.get(column.name, 0)))
        
        if column.operation == 'add':
            net += value
        elif column.operation == 'subtract':
            net -= value
    
    return net.quantize(Decimal('0.01'))


def set_payroll_password(tenant, password):
    """
    Set hashed payroll password for a tenant.
    
    Args:
        tenant: Tenant instance
        password (str): Plain text password
        
    Returns:
        bool: True if successful
    """
    if not password:
        return False
    
    tenant.payroll_password_hash = make_password(password)
    tenant.save(update_fields=['payroll_password_hash'])
    return True


def verify_payroll_password(tenant, password):
    """
    Verify payroll password for a tenant.
    
    Args:
        tenant: Tenant instance
        password (str): Plain text password to verify
        
    Returns:
        bool: True if password is correct
    """
    if not tenant.payroll_password_hash or not password:
        return False
    
    return check_password(password, tenant.payroll_password_hash)


def has_payroll_password(tenant):
    """
    Check if tenant has a payroll password set.
    
    Args:
        tenant: Tenant instance
        
    Returns:
        bool: True if password is set
    """
    return bool(tenant.payroll_password_hash)


def get_staff_with_profiles(tenant):
    """
    Get all active staff with StaffProfile for a tenant.
    Auto-fetches name and bank details.
    
    Args:
        tenant: Tenant instance
        
    Returns:
        QuerySet: CustomUser queryset with staff_profile prefetched
    """
    from documents.models import CustomUser
    
    return CustomUser.objects.filter(
        tenant=tenant,
        is_active=True,
        staff_profile__isnull=False
    ).select_related('staff_profile').order_by('first_name', 'last_name')


def auto_fill_staff_details(staff):
    """
    Auto-fill staff details from StaffProfile.
    
    Args:
        staff: CustomUser instance
        
    Returns:
        dict: Staff details (name, bank_name, account_number)
    """
    details = {
        'staff_name': staff.get_full_name() or staff.username,
        'bank_name': '',
        'account_number': ''
    }
    
    if hasattr(staff, 'staff_profile') and staff.staff_profile:
        profile = staff.staff_profile
        details['staff_name'] = profile.get_full_name()
        details['bank_name'] = profile.bank_account_name or ''
        details['account_number'] = profile.bank_account_number or ''
    
    return details


def get_payroll_summary(payroll):
    """
    Get summary statistics for a payroll.
    
    Args:
        payroll: Payroll instance
        
    Returns:
        dict: Summary with total_gross, total_net, employee_count
    """
    from django.db.models import Sum, Count
    
    summary = payroll.items.aggregate(
        total_gross=Sum('gross_amount'),
        total_net=Sum('net_amount'),
        employee_count=Count('id')
    )
    
    return {
        'total_gross': summary['total_gross'] or Decimal('0'),
        'total_net': summary['total_net'] or Decimal('0'),
        'employee_count': summary['employee_count'] or 0
    }


def copy_payroll_to_next_month(payroll):
    """
    Copy a payroll to the next month with same staff and amounts.
    
    Args:
        payroll: Payroll instance to copy
        
    Returns:
        Payroll: New payroll instance (not saved)
    """
    from documents.models import Payroll
    from datetime import timedelta
    from dateutil.relativedelta import relativedelta
    
    # Calculate next month dates
    next_period_start = payroll.period_start + relativedelta(months=1)
    next_period_end = payroll.period_end + relativedelta(months=1)
    
    # Create new payroll (don't save yet)
    new_payroll = Payroll(
        tenant=payroll.tenant,
        period_start=next_period_start,
        period_end=next_period_end,
        status='draft',
        custom_fields=payroll.custom_fields,
        notification_days_before=payroll.notification_days_before,
        payment_option='pay_now',
        created_by=payroll.created_by
    )
    
    return new_payroll


def validate_payroll_for_approval(payroll):
    """
    Validate if payroll is ready for approval submission.
    
    Args:
        payroll: Payroll instance
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if payroll.status != 'draft':
        return False, f"Payroll is already {payroll.status}"
    
    if not payroll.items.exists():
        return False, "Payroll has no items. Add staff payments first."
    
    # Check if all items have valid amounts
    invalid_items = payroll.items.filter(gross_amount__lte=0)
    if invalid_items.exists():
        return False, "Some payroll items have invalid gross amounts"
    
    return True, ""


def validate_payroll_for_payment(payroll, user):
    """
    Validate if payroll is ready for payment execution.
    
    Args:
        payroll: Payroll instance
        user: CustomUser attempting to pay
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not payroll.is_fully_approved:
        return False, "Payroll must be fully approved before payment"
    
    if payroll.status == 'paid':
        return False, "Payroll has already been paid"
    
    if not user_can_pay_payroll(user):
        return False, "You don't have permission to execute payments"
    
    if not has_payroll_password(payroll.tenant):
        return False, "Payroll password not set. Contact admin."
    
    return True, ""
