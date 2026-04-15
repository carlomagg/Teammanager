from django import template
from documents.models import CompanyProfile, UserProfile

register = template.Library()

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
        return user.user_profile
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