from django import template
from decimal import Decimal
from documents.models import CompanyProfile, UserProfile
register = template.Library()

@register.filter
def calculate_adjusted_amount(payment, wallet):
    """Calculate adjusted amount for a payment"""
    return wallet.calculate_adjusted_amount(payment.amount)

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def multiply(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def divide(value, arg):
    """Divide value by arg"""
    try:
        if float(arg) != 0:
            return float(value) / float(arg)
        return 0
    except (ValueError, TypeError):
        return value
    

@register.filter
def safe_company_profile(tenant):
    """Safely get company profile without raising DoesNotExist"""
    try:
        return tenant.company_profile
    except CompanyProfile.DoesNotExist:
        return None
    
@register.filter
def safe_user_profile(user):
    """Safely get user profile without raising DoesNotExist"""
    try:
        return user.user.user_profile
    except UserProfile.DoesNotExist:
        return None

@register.filter
def has_bank_verified(tenant):
    """Check if tenant has verified bank details"""
    try:
        profile = tenant.company_profile
        return profile and profile.bank_verified
    except CompanyProfile.DoesNotExist:
        return False