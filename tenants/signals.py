from django.db.models.signals import post_save, post_delete, pre_save
from django.db.models import Q
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal

from documents.viewfuncs.send_mails import send_trial_welcome_email
from .models import Subscription
from documents.models import CustomUser
import logging

logger = logging.getLogger(__name__)

@receiver(pre_save, sender='documents.CustomUser')
def store_original_tenant(sender, instance, **kwargs):
    """Store original tenant before save to detect changes"""
    if instance.pk:
        try:
            original = sender.objects.get(pk=instance.pk)
            instance._original_tenant = original.tenant
        except sender.DoesNotExist:
            instance._original_tenant = None

@receiver(post_delete, sender='documents.CustomUser')
def handle_tenant_user_deletion(sender, instance, **kwargs):
    """Handle subscription changes when tenant users are deleted"""
    from .models import Subscription, Credit
    
    if not instance.tenant_id:
        return
    
    try:
        active_sub = Subscription.objects.filter(
            tenant=instance.tenant_id,
            status='active'
        ).first()
        
        if active_sub:
            # Get updated user count after deletion
            from django.apps import apps
            CustomUser = apps.get_model('documents', 'CustomUser')
            current_user_count = CustomUser.objects.filter(tenant=instance.tenant_id).count()
            
            logger.info(f"User removed from tenant {instance.tenant.id}. New count: {current_user_count}")
            
            # Calculate credit for removed user
            old_count = current_user_count + 1
            credit_amount = active_sub.calculate_prorated_credit(old_count, current_user_count)
            
            if credit_amount > 0:
                # Create credit for future billing
                credit = Credit.objects.create(
                    tenant=instance.tenant,
                    subscription=active_sub,
                    credit_type='user_removal',
                    amount=credit_amount,
                    remaining_amount=credit_amount,
                    reason=f"User removed - credit for remaining days (User: {instance.email})",
                    expires_at=active_sub.end_date
                )
                
                logger.info(f"Credit of ${credit_amount} created for tenant {instance.tenant.id}")
            
            # Update subscription user count
            active_sub.current_user_count = current_user_count
            active_sub.last_user_count_update = timezone.now()
            active_sub.save(update_fields=['current_user_count', 'last_user_count_update'])
                
    except Exception as e:
        logger.error(f"Error handling user deletion: {str(e)}", exc_info=True)


@receiver(post_delete, sender=CustomUser)
def cleanup_user_subscription_status(sender, instance, **kwargs):
    """
    Optional: Log when a user is removed from a tenant
    """
    if instance.tenant_id and not instance.is_superuser:
        logger.info(f"User {instance.email} removed from tenant {instance.tenant_id}")


# @receiver(post_save, sender=Subscription)
# def update_users_on_subscription_change(sender, instance, created, **kwargs):
#     """
#     When a subscription is created or updated, update all affected users
#     """
#     # Handle tenant subscriptions
#     if instance.tenant_id:
#         # Get covered users based on subscription scope
#         covered_users = instance.get_covered_users()
        
#         # Determine status and end date based on subscription
#         if instance.status == 'active':
#             user_status = 'active'
#             user_end_date = instance.end_date
#         else:
#             # For non-active subscriptions, users are inactive
#             user_status = 'inactive'
#             user_end_date = None
        
#         # Update covered users
#         updated_count = covered_users.update(
#             subscription_status=user_status,
#             subscription_end_date=user_end_date,
#             subscription_plan=instance.plan if instance.status == 'active' else None
#         )
#         logger.info(f"Updated {updated_count} users for subscription {instance.id} to {user_status} until {user_end_date}")
    
#     # Handle individual user subscriptions
#     elif instance.user:
#         user = instance.user
        
#         if instance.status == 'active':
#             user.subscription_status = 'active'
#             user.subscription_end_date = instance.end_date
#             user.subscription_plan = instance.plan
#         else:
#             user.subscription_status = 'inactive'
#             user.subscription_end_date = None
#             user.subscription_plan = None
        
#         user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
#         logger.info(f"Updated user {user.email} to {user.subscription_status} until {user.subscription_end_date}")

# signals.py - REPLACE the old signal with this comprehensive one

@receiver(post_save, sender=Subscription)
def update_users_subscription_status(sender, instance, created, **kwargs):
    """
    When a subscription is created or updated, update all affected users.
    Handles both 'all' and 'selected' scopes for tenant subscriptions,
    as well as individual user subscriptions.
    """
    
    # Handle tenant subscriptions
    if instance.tenant:
        # Get covered users based on subscription scope
        covered_users = instance.get_covered_users()
        user_status = ''
        user_end_date = None
        user_plan = None
        # Determine status and end date based on subscription status
        if instance.status == 'active':
            user_status = 'active'
            user_end_date = instance.end_date
            user_plan = instance.plan
        
        # Update all covered users
        updated_count = covered_users.update(
            subscription_status=user_status,
            subscription_end_date=user_end_date,
            subscription_plan=user_plan
        )
        
        logger.info(f"Updated {updated_count} users for subscription {instance.id} "
                   f"(tenant: {instance.tenant.id}, scope: {instance.user_scope}, status: {instance.status})")
        
    # Handle individual user subscriptions
    elif instance.user:
        user = instance.user
        
        if instance.status == 'active':
            user.subscription_status = 'active'
            user.subscription_end_date = instance.end_date
            user.subscription_plan = instance.plan
        
        user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
        logger.info(f"Updated user {user.email} to {user.subscription_status} for subscription {instance.id}")

# @receiver(post_save, sender=Subscription)
# def update_users_subscription_status(sender, instance, created, **kwargs):
#     """
#     When a tenant subscription is created or updated, update all users in that tenant
#     BUT only if the subscription covers all users
#     """
#     # Only process tenant subscriptions (not individual user subscriptions)
#     if not instance.tenant_id:
#         return
    
#     # Only update ALL users if the subscription covers ALL users
#     if instance.user_scope != 'all':
#         # For 'selected' scope, the other signal handles it
#         return
    
#     logger.info(f"Subscription {instance.id} for tenant {instance.tenant.id} changed to {instance.status}")
    
#     # Get all users in this tenant (excluding superusers)
#     users = CustomUser.objects.filter(
#         tenant=instance.tenant,
#         is_superuser=False
#     )
    
#     # Determine the status and end date to set for users
#     if instance.status == 'active':
#         user_status = 'active'
#         end_date = instance.end_date
#     else:
#         user_status = 'inactive'
#         end_date = None
    
#     # Update all users
#     updated_count = users.update(
#         subscription_status=user_status,
#         subscription_end_date=end_date
#     )
#     logger.info(f"Updated {updated_count} users in tenant {instance.tenant.id} to status '{user_status}' with end date {end_date}")


@receiver(post_save, sender=CustomUser)
def set_new_user_subscription_status(sender, instance, created, **kwargs):
    """
    When a new user is created, give them a 7-day trial instead of auto-coverage.
    Send welcome email with trial information.
    """
    if not created or instance.is_superuser:
        return
    
    from django.db.models import Q
    from datetime import timedelta
    from django.utils import timezone
    
    # Calculate trial end date (7 days from now)
    trial_end_date = timezone.now().date() + timedelta(days=7)
    
    # For tenant users
    if instance.tenant:
        instance.subscription_status = 'trial'
        instance.subscription_end_date = trial_end_date
        instance.subscription_plan = None  # No plan assigned during trial
        instance.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
        
        # logger.info(f"New tenant user {instance.email} started 7-day trial (tenant has active subscription)")
        
        # Send trial welcome email to tenant user
        send_trial_welcome_email(
            user=instance,
            tenant=instance.tenant,
            days=7,
            is_tenant_user=True
        )
    # For individual/personal users
    elif instance.is_personal:
        # Give individual user a 7-day trial
        instance.subscription_status = 'trial'
        instance.subscription_end_date = trial_end_date
        instance.subscription_plan = None
        instance.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
        
        logger.info(f"New personal user {instance.email} started 7-day trial")
        
        # Send trial welcome email to personal user
        send_trial_welcome_email(
            user=instance,
            days=7,
            is_tenant_user=False
        )


# @receiver(post_save, sender=CustomUser)
# def handle_user_tenant_assignment(sender, instance, created, **kwargs):
#     """
#     When a user is assigned to a tenant, check if they should be covered by any existing subscription
#     """
#     # Skip if this is a new user (handled by set_new_user_subscription_status)
#     if created:
#         return
    
#     # Check if tenant changed
#     if hasattr(instance, '_original_tenant') and instance._original_tenant:
#         old_tenant = instance._original_tenant
#         new_tenant = instance.tenant
        
#         if old_tenant != new_tenant:
#             logger.info(f"User {instance.email} moved from tenant {old_tenant.id if old_tenant else None} to {new_tenant.id if new_tenant else None}")
            
#             # Remove from old tenant's subscriptions if needed
#             if old_tenant:
#                 # Find all active subscriptions in old tenant
#                 old_subscriptions = Subscription.objects.filter(
#                     tenant=old_tenant,
#                     status='active'
#                 ).filter(
#                     Q(user_scope='selected', covered_users=instance) | Q(user_scope='all')
#                 )
                
#                 for sub in old_subscriptions:
#                     if sub.user_scope == 'selected':
#                         sub.covered_users.remove(instance)
#                     elif sub.user_scope == 'all':
#                         # Re-evaluate user's status based on all users subscription
#                         sub.update_covered_user_status()
            
#             # Check if new tenant has any active subscriptions
#             if new_tenant:
#                 new_subscriptions = Subscription.objects.filter(
#                     tenant=new_tenant,
#                     status='active'
#                 ).order_by('-created_at')
                
#                 if new_subscriptions.exists():
#                     # User is covered if there's an 'all' subscription or they're specifically added
#                     all_sub = new_subscriptions.filter(user_scope='all').first()
#                     if all_sub:
#                         # User is automatically covered
#                         all_sub.update_covered_user_status()
#                     else:
#                         # Check if any selected subscription includes this user
#                         selected_sub = new_subscriptions.filter(
#                             user_scope='selected',
#                             covered_users=instance
#                         ).first()
                        
#                         if selected_sub:
#                             instance.subscription_status = 'active'
#                             instance.subscription_end_date = selected_sub.end_date
#                             instance.subscription_plan = selected_sub.plan
#                             instance.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
#                         else:
#                             # No subscription covers this user
#                             instance.subscription_status = 'inactive'
#                             instance.subscription_end_date = None
#                             instance.subscription_plan = None
#                             instance.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])