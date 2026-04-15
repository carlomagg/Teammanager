from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone

from django.db import models
from .models import Subscription
import logging

logger = logging.getLogger(__name__)

def subscription_required(view_func):
    """Decorator to check if user has active subscription or is exempt"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        
        # Superusers are always exempt
        if user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # Check if user is staff/exempt (you can customize this)
        if user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Check for explicit exemption
        if hasattr(user, 'subscription_exemption') and user.subscription_exemption:
            return view_func(request, *args, **kwargs)
        
        # Check if user has access through subscription
        has_access = False
        access_type = None
        
        # Check individual user subscription first (highest priority)
        individual_sub = Subscription.objects.filter(
            user=user,
            status='active'
        ).first()
        
        if individual_sub:
            # Check if free access hasn't expired
            if individual_sub.is_free and individual_sub.free_expires_at:
                if individual_sub.free_expires_at < timezone.now().date():
                    logger.info(f"Individual free subscription expired for user {user.id}")
                    messages.warning(request, "Your free access has expired. Please subscribe to continue.")
                else:
                    has_access = True
                    access_type = "individual"
            elif individual_sub.is_free:
                has_access = True
                access_type = "individual"
            else:
                has_access = True
                access_type = "individual"
        
        # If no individual subscription, check tenant subscriptions
        if not has_access and hasattr(user, 'tenant') and user.tenant:
            # Check if user is covered by any active tenant subscription
            covered_subscriptions = Subscription.objects.filter(
                tenant=user.tenant,
                status='active'
            ).filter(
                models.Q(user_scope='all') | 
                models.Q(user_scope='selected', covered_users=user)
            )
            
            # Get the most recent active subscription
            active_sub = covered_subscriptions.order_by('-created_at').first()
            
            if active_sub:
                # Check if free access hasn't expired
                if active_sub.is_free and active_sub.free_expires_at:
                    if active_sub.free_expires_at < timezone.now().date():
                        logger.info(f"Free subscription expired for tenant {user.tenant.id}, user {user.id}")
                        messages.warning(request, "Your organization's free access has expired. Please subscribe to continue.")
                    else:
                        has_access = True
                        access_type = f"tenant_{active_sub.user_scope}"
                elif active_sub.is_free:
                    has_access = True
                    access_type = f"tenant_{active_sub.user_scope}"
                else:
                    has_access = True
                    access_type = f"tenant_{active_sub.user_scope}"
                
                if has_access:
                    logger.info(f"User {user.id} has access via {access_type} subscription")
        
        if has_access:
            return view_func(request, *args, **kwargs)
        else:
            # Check if user is a tenant user but no subscription covers them
            if hasattr(user, 'tenant') and user.tenant:
                # Check if there are any active subscriptions in the tenant
                any_active = Subscription.objects.filter(
                    tenant=user.tenant,
                    status='active'
                ).exists()
                
                if any_active:
                    messages.error(
                        request, 
                        "You are not included in your organization's current subscription. "
                        "Please contact your administrator to be added to the subscription."
                    )
                else:
                    messages.error(request, "Your organization does not have an active subscription.")
            else:
                messages.error(request, "You need an active subscription to access this page.")
            
            return redirect('subscription_base')
    
    return _wrapped_view

def check_subscription_access(user):
    """
    Utility function to check if user has subscription access
    Returns: (has_access, access_details)
    """
    if user.is_superuser or user.is_staff:
        return True, {"type": "superuser/staff"}
    
    if hasattr(user, 'subscription_exemption') and user.subscription_exemption:
        return True, {"type": "exempt"}
    
    # Check individual user subscription first
    individual_sub = Subscription.objects.filter(
        user=user,
        status='active'
    ).first()
    
    if individual_sub:
        if individual_sub.is_free and individual_sub.free_expires_at:
            if individual_sub.free_expires_at < timezone.now().date():
                return False, {"reason": "Free subscription expired", "expired_at": individual_sub.free_expires_at}
        return True, {
            "type": "individual",
            "subscription_id": individual_sub.id,
            "plan": individual_sub.plan.name,
            "end_date": individual_sub.end_date,
            "is_free": individual_sub.is_free
        }
    
    # Check tenant subscriptions
    if hasattr(user, 'tenant') and user.tenant:
        # Find subscriptions that cover this user
        covered_subscriptions = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).filter(
            models.Q(user_scope='all') | 
            models.Q(user_scope='selected', covered_users=user)
        ).order_by('-created_at')
        
        active_sub = covered_subscriptions.first()
        
        if active_sub:
            if active_sub.is_free and active_sub.free_expires_at:
                if active_sub.free_expires_at < timezone.now().date():
                    return False, {
                        "reason": "Free subscription expired",
                        "expired_at": active_sub.free_expires_at,
                        "tenant": user.tenant.id
                    }
            return True, {
                "type": f"tenant_{active_sub.user_scope}",
                "subscription_id": active_sub.id,
                "plan": active_sub.plan.name,
                "end_date": active_sub.end_date,
                "user_scope": active_sub.user_scope,
                "covered_users_count": active_sub.get_covered_user_count(),
                "is_free": active_sub.is_free
            }
        
        # Check if there are any active subscriptions in the tenant
        any_active = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).exists()
        
        if any_active:
            return False, {
                "reason": "User not covered by any subscription",
                "tenant": user.tenant.id,
                "has_active_subscriptions": True
            }
        else:
            return False, {
                "reason": "No active subscriptions in tenant",
                "tenant": user.tenant.id
            }
    
    # No subscriptions found
    return False, {"reason": "No active subscription"}

def get_user_subscription_info(user):
    """
    Get detailed subscription information for a user
    Returns: dict with subscription details or None
    """
    if user.is_superuser:
        return {
            "has_access": True,
            "type": "superuser",
            "message": "Superuser access"
        }
    
    if user.is_staff:
        return {
            "has_access": True,
            "type": "staff",
            "message": "Staff access"
        }
    
    # Check individual subscription
    individual_sub = Subscription.objects.filter(
        user=user,
        status='active'
    ).first()
    
    if individual_sub:
        return {
            "has_access": True,
            "type": "individual",
            "subscription": individual_sub,
            "plan": individual_sub.plan.name,
            "start_date": individual_sub.start_date,
            "end_date": individual_sub.end_date,
            "is_free": individual_sub.is_free,
            "remaining_days": (individual_sub.end_date - timezone.now().date()).days if individual_sub.end_date else 0
        }
    
    # Check tenant subscriptions
    if hasattr(user, 'tenant') and user.tenant:
        covered_subs = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).filter(
            models.Q(user_scope='all') | 
            models.Q(user_scope='selected', covered_users=user)
        ).order_by('-created_at')
        
        active_sub = covered_subs.first()
        
        if active_sub:
            # Get all covered users for context
            covered_users = active_sub.get_covered_users()
            
            return {
                "has_access": True,
                "type": f"tenant_{active_sub.user_scope}",
                "subscription": active_sub,
                "plan": active_sub.plan.name,
                "start_date": active_sub.start_date,
                "end_date": active_sub.end_date,
                "user_scope": active_sub.user_scope,
                "covered_users_count": covered_users.count(),
                "is_free": active_sub.is_free,
                "remaining_days": (active_sub.end_date - timezone.now().date()).days if active_sub.end_date else 0,
                "tenant": user.tenant
            }
        
        # No subscription covering this user, but check if there are any subscriptions
        any_active = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).exists()
        
        if any_active:
            return {
                "has_access": False,
                "type": "tenant_user_not_covered",
                "message": "You are not covered by any subscription in your organization",
                "tenant": user.tenant
            }
        else:
            return {
                "has_access": False,
                "type": "tenant_no_subscription",
                "message": "Your organization has no active subscription",
                "tenant": user.tenant
            }
    
    return {
        "has_access": False,
        "type": "no_subscription",
        "message": "No active subscription found"
    }

def require_subscription_access(subscription_type=None, min_users=None):
    """
    Advanced decorator that can check specific subscription requirements
    
    Args:
        subscription_type: Optional plan type name to check
        min_users: Minimum number of covered users required (for tenant subscriptions)
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            
            # Superusers bypass all checks
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            has_access, access_info = check_subscription_access(user)
            
            if not has_access:
                messages.error(request, access_info.get("message", "Subscription required"))
                return redirect('subscription_base')
            
            # Check subscription type if specified
            if subscription_type:
                if access_info.get("type") == "individual":
                    sub = Subscription.objects.filter(user=user, status='active').first()
                    if sub and sub.plan.name.lower() != subscription_type.lower():
                        messages.error(request, f"This feature requires a {subscription_type} subscription")
                        return redirect('subscription_base')
                elif "tenant" in access_info.get("type", ""):
                    sub = Subscription.objects.filter(
                        tenant=user.tenant,
                        status='active'
                    ).filter(
                        models.Q(user_scope='all') | 
                        models.Q(user_scope='selected', covered_users=user)
                    ).first()
                    if sub and sub.plan.name.lower() != subscription_type.lower():
                        messages.error(request, f"This feature requires a {subscription_type} subscription")
                        return redirect('subscription_base')
            
            # Check minimum users if specified
            if min_users and "tenant" in access_info.get("type", ""):
                sub = Subscription.objects.filter(
                    tenant=user.tenant,
                    status='active'
                ).filter(
                    models.Q(user_scope='all') | 
                    models.Q(user_scope='selected', covered_users=user)
                ).first()
                
                if sub:
                    covered_count = sub.get_covered_user_count()
                    if covered_count < min_users:
                        messages.error(
                            request, 
                            f"This feature requires at least {min_users} users in your subscription. "
                            f"Your current subscription covers {covered_count} users."
                        )
                        return redirect('subscription_base')
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator


# Additional helper functions for subscription checks

def sync_user_subscription_status(user):
    """
    Synchronize a user's subscription status with their actual subscription coverage.
    This should be called periodically or when user/tenant changes.
    """
    if not user.is_authenticated or user.is_superuser:
        return
    
    today = timezone.now().date()
    
    # Check individual subscription
    individual_sub = Subscription.objects.filter(
        user=user,
        status='active'
    ).first()
    
    if individual_sub:
        if individual_sub.end_date and individual_sub.end_date >= today:
            user.subscription_status = 'active'
            user.subscription_end_date = individual_sub.end_date
            user.subscription_plan = individual_sub.plan
            user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
            return True
    
    # Check tenant coverage
    if hasattr(user, 'tenant') and user.tenant:
        covered_sub = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).filter(
            models.Q(user_scope='all') | 
            models.Q(user_scope='selected', covered_users=user)
        ).order_by('-created_at').first()
        
        if covered_sub and covered_sub.end_date and covered_sub.end_date >= today:
            user.subscription_status = 'active'
            user.subscription_end_date = covered_sub.end_date
            user.subscription_plan = covered_sub.plan
            user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
            return True
    
    # No active coverage
    user.subscription_status = 'inactive'
    user.subscription_end_date = None
    user.subscription_plan = None
    user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
    return False

def get_user_subscription_details(user):
    """
    Get detailed subscription information for a user
    Returns a comprehensive dict with all subscription details
    """
    if user.is_superuser:
        return {
            'has_access': True,
            'type': 'superuser',
            'message': 'Superuser access - no restrictions'
        }
    
    if user.is_staff:
        return {
            'has_access': True,
            'type': 'staff',
            'message': 'Staff access - limited restrictions'
        }
    
    today = timezone.now().date()
    
    # Check individual subscription
    individual_sub = Subscription.objects.filter(
        user=user,
        status='active'
    ).first()
    
    if individual_sub:
        days_left = (individual_sub.end_date - today).days if individual_sub.end_date else None
        
        return {
            'has_access': True,
            'type': 'individual',
            'subscription': individual_sub,
            'subscription_id': individual_sub.id,
            'plan_name': individual_sub.plan.name,
            'plan_price': individual_sub.plan.price,
            'start_date': individual_sub.start_date,
            'end_date': individual_sub.end_date,
            'days_left': days_left,
            'is_free': individual_sub.is_free,
            'free_reason': individual_sub.free_reason if individual_sub.is_free else None,
            'status': individual_sub.status,
            'auto_renew': individual_sub.auto_renew
        }
    
    # Check tenant coverage
    if hasattr(user, 'tenant') and user.tenant:
        covered_sub = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).filter(
            models.Q(user_scope='all') | 
            models.Q(user_scope='selected', covered_users=user)
        ).order_by('-created_at').first()
        
        if covered_sub:
            days_left = (covered_sub.end_date - today).days if covered_sub.end_date else None
            covered_users = covered_sub.get_covered_users()
            
            return {
                'has_access': True,
                'type': f'tenant_{covered_sub.user_scope}',
                'subscription': covered_sub,
                'subscription_id': covered_sub.id,
                'plan_name': covered_sub.plan.name,
                'plan_price': covered_sub.plan.price,
                'start_date': covered_sub.start_date,
                'end_date': covered_sub.end_date,
                'days_left': days_left,
                'is_free': covered_sub.is_free,
                'free_reason': covered_sub.free_reason if covered_sub.is_free else None,
                'status': covered_sub.status,
                'user_scope': covered_sub.user_scope,
                'covered_users_count': covered_users.count(),
                'tenant': user.tenant,
                'tenant_name': user.tenant.name
            }
        
        # Check if tenant has any subscription
        any_sub = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).exists()
        
        if any_sub:
            return {
                'has_access': False,
                'type': 'not_covered',
                'message': 'Your organization has an active subscription, but you are not covered by it.',
                'tenant': user.tenant,
                'tenant_name': user.tenant.name
            }
        else:
            return {
                'has_access': False,
                'type': 'no_tenant_subscription',
                'message': 'Your organization does not have an active subscription.',
                'tenant': user.tenant,
                'tenant_name': user.tenant.name
            }
    
    return {
        'has_access': False,
        'type': 'no_subscription',
        'message': 'No active subscription found.'
    }

def get_subscription_warning_message(access_info):
    """
    Generate a warning message based on subscription details
    """
    if not access_info.get('has_access'):
        return None
    
    days_left = access_info.get('days_left')
    sub_type = access_info.get('type', 'subscription')
    is_free = access_info.get('is_free', False)
    
    if days_left is None:
        return None
    
    # Format the subscription type for display
    if 'tenant' in sub_type:
        sub_type_display = "organization's subscription"
    elif sub_type == 'individual':
        sub_type_display = "your subscription"
    else:
        sub_type_display = "subscription"
    
    if is_free and days_left > 3:
        return None
    
    if days_left <= 0:
        return f"Your {sub_type_display} has expired. Please renew immediately to avoid service interruption."
    elif days_left == 1:
        return f"⚠️ Your {sub_type_display} ends TOMORROW! Please renew now to avoid service interruption."
    elif days_left <= 3:
        return f"⚠️ Your {sub_type_display} ends in {days_left} days. Please renew soon to continue access."
    elif days_left <= 7:
        return f"ℹ️ Your {sub_type_display} ends in {days_left} days. Don't forget to renew."
    
    return None