from urllib import request

from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from documents.viewfuncs.helper_funcs.paystack import initialize_paystack_payment
from django.db.models import Q, Sum
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from decimal import Decimal
from django.contrib.auth.decorators import login_required, user_passes_test
from datetime import datetime, timedelta
import logging
from django.apps import apps
from documents.viewfuncs.rba_decorators import is_admin
from ..models import Subscription, SubscriptionType, Credit, Tenant
from documents.models import CustomUser, Payment, ContentType
from ..forms import CreditApplyForm, SubscriptionForm, SubscriptionAdjustmentForm
from django.views.decorators.http import require_GET


logger = logging.getLogger(__name__)


# @login_required
# @user_passes_test(lambda u: is_admin(u) or u.is_personal)
# def client_subscriptions(request):
#     """List all subscriptions for the current user/tenant"""
#     from django.utils import timezone
#     from datetime import timedelta
    
#     today = timezone.now().date()
    
#     # Get base queryset
#     if hasattr(request.user, 'tenant') and request.user.tenant:
#         # Tenant user - show tenant subscriptions
#         subscriptions = Subscription.objects.filter(tenant=request.user.tenant)
#     else:
#         # Individual user - show their subscriptions
#         subscriptions = Subscription.objects.filter(user=request.user)
    
#     plans = SubscriptionType.objects.all().order_by('-is_active', 'price')
    
#     # Get filter parameters
#     status = request.GET.get('status')
#     plan_filter = request.GET.get('plan')
    
#     # Apply filters
#     if status:
#         subscriptions = subscriptions.filter(status=status)
    
#     if plan_filter:
#         subscriptions = subscriptions.filter(plan_id=plan_filter)
    
#     # Calculate stats
#     total_subscriptions = subscriptions.count()
#     active_subscriptions = subscriptions.filter(status='active').count()
#     pending_subscriptions = subscriptions.filter(status='pending').count()
#     expired_subscriptions = subscriptions.filter(status='expired').count()
#     cancelled_subscriptions = subscriptions.filter(status='cancelled').count()
#     revoked_subscriptions = subscriptions.filter(status='revoked').count()
    
#     # Calculate expiring soon (active subscriptions ending in next 7 days)
#     expiring_soon = subscriptions.filter(
#         status='active',
#         end_date__gte=today,
#         end_date__lte=today + timedelta(days=7)
#     ).count()
    
#     # Calculate monthly spend (sum of active subscription monthly rates)
#     monthly_spend = 0
#     for sub in subscriptions.filter(status='active'):
#         monthly_spend += sub.get_current_monthly_rate()
    
#     # Pagination
#     paginator = Paginator(subscriptions.order_by('-created_at'), 10)
#     page = request.GET.get('page')
#     subscriptions = paginator.get_page(page)
    
#     context = {
#         'subscriptions': subscriptions,
#         'status_filter': status,
#         'plan_filter': plan_filter,
#         'plans': plans,
#         'total_subscriptions': total_subscriptions,
#         'active_subscriptions': active_subscriptions,
#         'pending_subscriptions': pending_subscriptions,
#         'expired_subscriptions': expired_subscriptions,
#         'cancelled_subscriptions': cancelled_subscriptions,
#         'revoked_subscriptions': revoked_subscriptions,
#         'expiring_soon': expiring_soon,
#         'monthly_spend': monthly_spend,
#         'now': today,
#     }
#     return render(request, 'subscriptions/owner_subscriptions_list.html', context)


@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal)
def client_subscriptions(request):
    """List all subscriptions for the current user/tenant"""
    from django.utils import timezone
    from datetime import timedelta
    
    today = timezone.now().date()
    
    # Get base queryset based on user type
    if hasattr(request.user, 'tenant') and request.user.tenant:
        # Tenant user - show tenant subscriptions
        # But also show any individual subscriptions they might have
        subscriptions = Subscription.objects.filter(tenant=request.user.tenant)
    else:
        # Individual user - show their subscriptions
        subscriptions = Subscription.objects.filter(user=request.user)
    
    # Get all active plans for filtering
    plans = SubscriptionType.objects.all().order_by('-is_active', 'price')
    
    # Get filter parameters
    status = request.GET.get('status')
    plan_filter = request.GET.get('plan')
    user_scope = request.GET.get('user_scope')  # New filter for user scope
    
    # Apply filters
    if status:
        subscriptions = subscriptions.filter(status=status)
    
    if plan_filter:
        subscriptions = subscriptions.filter(plan_id=plan_filter)
    
    if user_scope and hasattr(request.user, 'tenant'):
        subscriptions = subscriptions.filter(user_scope=user_scope)
    
    # Calculate stats with new logic
    total_subscriptions = subscriptions.count()
    active_subscriptions = subscriptions.filter(status='active').count()
    pending_subscriptions = subscriptions.filter(status='pending').count()
    expired_subscriptions = subscriptions.filter(status='expired').count()
    cancelled_subscriptions = subscriptions.filter(status='cancelled').count()
    revoked_subscriptions = subscriptions.filter(status='revoked').count()
    
    # Calculate expiring soon (active subscriptions ending in next 7 days)
    expiring_soon = subscriptions.filter(
        status='active',
        end_date__gte=today,
        end_date__lte=today + timedelta(days=7)
    ).count()
    
    # Calculate monthly spend (sum of active subscription monthly rates)
    monthly_spend = 0
    for sub in subscriptions.filter(status='active'):
        monthly_spend += sub.get_current_monthly_rate()
    
    # Get user coverage info for tenant users
    user_coverage_info = None
    if hasattr(request.user, 'tenant') and request.user.tenant:
        # Check which subscriptions cover this user
        covering_subs = Subscription.objects.filter(
            tenant=request.user.tenant,
            status='active'
        ).filter(
            models.Q(user_scope='all') | 
            models.Q(user_scope='selected', covered_users=request.user)
        )
        
        user_coverage_info = {
            'covered': covering_subs.exists(),
            'subscriptions': covering_subs,
            'coverage_count': covering_subs.count()
        }
    
    # Pagination
    paginator = Paginator(subscriptions.order_by('-created_at'), 10)
    page = request.GET.get('page')
    subscriptions = paginator.get_page(page)
    
    context = {
        'subscriptions': subscriptions,
        'status_filter': status,
        'plan_filter': plan_filter,
        'user_scope_filter': user_scope,
        'plans': plans,
        'total_subscriptions': total_subscriptions,
        'active_subscriptions': active_subscriptions,
        'pending_subscriptions': pending_subscriptions,
        'expired_subscriptions': expired_subscriptions,
        'cancelled_subscriptions': cancelled_subscriptions,
        'revoked_subscriptions': revoked_subscriptions,
        'expiring_soon': expiring_soon,
        'monthly_spend': monthly_spend,
        'now': today,
        'user_coverage_info': user_coverage_info,
        'is_tenant_user': hasattr(request.user, 'tenant') and request.user.tenant,
    }
    return render(request, 'subscriptions/owner_subscriptions_list.html', context)



@login_required
def create_subscription(request):
    """Create a new subscription with duplicate prevention and payment cleanup"""
    
    def calculate_subscription_dates(subscription, start_date):
        """Helper to calculate trial and end dates based on duration_months"""
        subscription.trial_end_date = start_date + timedelta(days=7)
        
        # Use duration_months to calculate end date
        if subscription.promo and subscription.promo.duration_days:
            subscription.end_date = start_date + timedelta(days=subscription.promo.duration_days)
        elif subscription.duration_months:
            # Calculate end date based on months (using actual month lengths)
            from dateutil.relativedelta import relativedelta
            subscription.end_date = start_date + relativedelta(months=int(subscription.duration_months))
        else:
            # Fallback to plan duration for backward compatibility
            subscription.end_date = start_date + timedelta(days=subscription.plan.duration)
        
        return subscription
    
    def mark_old_payments_abandoned(subscription, reason="new_subscription_created"):
        """Mark old pending payments as abandoned"""
        from django.contrib.contenttypes.models import ContentType
        
        old_payments = Payment.objects.filter(
            content_type=ContentType.objects.get_for_model(subscription),
            object_id=subscription.id,
            status='pending'
        )
        
        count = old_payments.count()
        for payment in old_payments:
            payment.status = 'abandoned'
            payment.metadata = payment.metadata or {}
            payment.metadata['abandoned_reason'] = reason
            payment.metadata['abandoned_at'] = timezone.now().isoformat()
            payment.save()
        
        if count > 0:
            logger.info(f"Marked {count} old payments as abandoned for subscription {subscription.id}")
        return count
    
    if request.method == 'POST':
        # Add debug logging
        print("=== POST DATA RECEIVED ===")
        print("POST keys:", request.POST.keys())
        print("selected_users from POST:", request.POST.getlist('selected_users'))
        print("user_scope:", request.POST.get('user_scope'))
        print("plan:", request.POST.get('plan'))
        print("tenant:", request.POST.get('tenant'))
        print("duration_months:", request.POST.get('duration_months'))
        print("==========================")
        
        form = SubscriptionForm(request.POST, request=request)
        if form.is_valid():
            print("Form is VALID")
            cleaned_data = form.cleaned_data
            tenant = cleaned_data.get('tenant')
            user = cleaned_data.get('user')
            user_scope = cleaned_data.get('user_scope')
            selected_users = cleaned_data.get('selected_users', [])
            duration_months = cleaned_data.get('duration_months', 1)
            no_of_tenant_users = 0
            if request.user.tenant:
                no_of_tenant_users = CustomUser.objects.filter(tenant=request.user.tenant, is_superuser=False).count()
                print(f"Total tenant users for {request.user.tenant}: {no_of_tenant_users}")  # Debug

            
            # Check for existing pending subscriptions
            existing_pending = None
            if tenant:
                # For tenant subscriptions, check by tenant
                existing_pending = Subscription.objects.filter(
                    tenant=tenant,
                    status='pending',
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).order_by('-created_at').first()
                # no_of_tenant_users = CustomUser.objects.filter(tenant=request.user.tenant).count() if hasattr(request.user, 'tenant') and request.user.tenant else 0
            elif user:
                existing_pending = Subscription.objects.filter(
                    user=user,
                    status='pending',
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).order_by('-created_at').first()
            
            # Calculate start date
            today = timezone.now().date()
            active_sub = None
            
            if tenant:
                # For tenant, check if any active subscription exists
                active_sub = Subscription.objects.filter(
                    tenant=tenant,
                    status='active',
                    end_date__gte=today
                ).order_by('-end_date').first()
            elif user:
                active_sub = Subscription.objects.filter(
                    user=user,
                    status='active',
                    end_date__gte=today
                ).order_by('-end_date').first()
            
            if active_sub and active_sub.end_date and active_sub.end_date > today:
                start_date = active_sub.end_date + timedelta(days=1)
                logger.info(f"Active subscription ends {active_sub.end_date}, new starts {start_date}")
            else:
                start_date = today
            
            if existing_pending:
                # Mark old payments as abandoned
                mark_old_payments_abandoned(existing_pending, "subscription_updated")
                
                # Update existing pending subscription
                subscription = existing_pending
                subscription.plan = cleaned_data['plan']
                subscription.billing_cycle = cleaned_data.get('billing_cycle', 'monthly')
                subscription.promo = cleaned_data.get('promo')
                subscription.promo_code = cleaned_data.get('promo_code')
                subscription.start_date = start_date
                subscription.user_scope = user_scope
                subscription.duration_months = duration_months
                
                # Save subscription first
                subscription.save()
                
                # Update covered users
                if tenant and user_scope == 'selected':
                    subscription.covered_users.set(selected_users)
                elif tenant and user_scope == 'all':
                    subscription.covered_users.clear()
                
                # Recalculate dates
                subscription = calculate_subscription_dates(subscription, start_date)
                subscription.save()
                
                messages.info(request, 'Updated your pending subscription. Previous payment attempts have been cleared.')
                logger.info(f"Updated existing pending subscription {subscription.id}")
            else:
                # Create new subscription
                subscription = Subscription(
                    tenant=tenant,
                    user=user,
                    plan=cleaned_data['plan'],
                    billing_cycle=cleaned_data.get('billing_cycle', 'monthly'),
                    promo=cleaned_data.get('promo'),
                    promo_code=cleaned_data.get('promo_code'),
                    status='pending',
                    start_date=start_date,
                    user_scope=user_scope,
                    duration_months=duration_months,
                )
                
                # Save subscription
                subscription.save()
                
                # Add covered users for tenant subscriptions
                if tenant and user_scope == 'selected':
                    subscription.covered_users.set(selected_users)
                
                # Calculate dates
                subscription = calculate_subscription_dates(subscription, start_date)
                subscription.save()
                
                messages.success(request, 'Subscription created successfully!')
                logger.info(f"Created new subscription {subscription.id}")
            
            # Store subscription data in session for potential back navigation
            request.session['last_subscription_data'] = {
                'subscription_id': subscription.id,
                'plan_id': subscription.plan.id,
                'plan_name': subscription.plan.name,
                'plan_price': float(subscription.plan.get_effective_price()),
                'duration_months': subscription.duration_months,
                'user_scope': subscription.user_scope,
                'tenant_id': subscription.tenant.id if subscription.tenant else None,
                'user_id': subscription.user.id if subscription.user else None,
                'selected_users': list(subscription.covered_users.values_list('id', flat=True)) if subscription.user_scope == 'selected' else []
            }
            
            # Check if free
            base_price = subscription.plan.get_effective_price()
            is_free = (subscription.promo and subscription.promo.discount_type == 'full') or base_price == 0
            
            if is_free:
                subscription.status = 'active'
                subscription.save()
                
                # Create payment record for zero amount
                from django.contrib.contenttypes.models import ContentType
                Payment.objects.create(
                    content_type=ContentType.objects.get_for_model(subscription),
                    object_id=subscription.id,
                    tenant=subscription.tenant,
                    owner=subscription.user,
                    payment_type="subscription",
                    direction="incoming",
                    amount=Decimal('0.00'),
                    net_amount=Decimal('0.00'),
                    status="success",
                    description=f"Free subscription: {subscription.plan.name}",
                    created_by=request.user,
                )
                
                messages.success(request, 'Subscription activated successfully!')
                return redirect('subscription_detail', pk=subscription.id)
            else:
                return redirect('subscription_payment_breakdown', subscription_id=subscription.id)
        else:
            print("=== FORM ERRORS ===")
            print(form.errors)
            print("Form data:", form.data)
            print("===================")
            
            # Store form errors and data in session for restoration
            request.session['form_errors'] = str(form.errors)
            request.session['form_data'] = request.POST.dict()
            
            # Instead of redirecting back, we need to re-render with errors
            plans = SubscriptionType.objects.filter(is_active=True)
            context = {
                'form': form,
                'plans': plans,
                'is_create': True,
                'no_of_tenant_users': no_of_tenant_users,
                'restoring': request.session.get('restoring_subscription', False),
                'restore_plan_id': request.session.get('restore_plan_id'),
                'restore_duration_months': request.session.get('restore_duration_months'),
                'restore_user_scope': request.session.get('restore_user_scope'),
                'restore_selected_users': request.session.get('restore_selected_users', []),
            }
            return render(request, 'subscriptions/subscription_form.html', context)
    else:
        if request.user.is_authenticated and hasattr(request.user, 'tenant') and request.user.tenant:
            no_of_tenant_users = CustomUser.objects.filter(
                tenant=request.user.tenant, 
                is_superuser=False
            ).count()
            print(f"GET request - Total tenant users: {no_of_tenant_users}")  # Debug

        # Check if we're restoring from payment breakdown
        restore = request.GET.get('restore')
        initial_data = {}
        
        # Try to restore from session first
        if restore and request.session.get('last_subscription_data'):
            last_data = request.session.get('last_subscription_data')
            initial_data = {
                'plan': last_data.get('plan_id'),
                'duration_months': last_data.get('duration_months'),
                'user_scope': last_data.get('user_scope'),
            }
            
            # Also store in a separate session variable for the template to use
            request.session['restore_selected_users'] = last_data.get('selected_users', [])
            request.session['restore_plan_id'] = last_data.get('plan_id')
            request.session['restore_duration_months'] = last_data.get('duration_months')
            request.session['restore_user_scope'] = last_data.get('user_scope')
            
            # Clear the session data after restoring (optional)
            # del request.session['last_subscription_data']
            
            # Add a flag to indicate restoration
            request.session['restoring_subscription'] = True
            
        elif request.GET.get('scope') == 'selected':
            initial_data['user_scope'] = 'selected'
        
        # Check if there's a pending subscription being edited
        elif request.GET.get('pending_id'):
            try:
                pending_sub = Subscription.objects.get(id=request.GET.get('pending_id'), status='pending')
                initial_data = {
                    'plan': pending_sub.plan.id,
                    'duration_months': pending_sub.duration_months,
                    'user_scope': pending_sub.user_scope,
                }
                request.session['restore_selected_users'] = list(pending_sub.covered_users.values_list('id', flat=True))
                request.session['restoring_subscription'] = True
            except Subscription.DoesNotExist:
                pass
        
        form = SubscriptionForm(request=request, initial=initial_data)
        
        # If we have a restore flag, add it to the context
        context_extra = {}
        if request.session.get('restoring_subscription'):
            context_extra['restoring'] = True
            context_extra['restore_plan_id'] = request.session.get('restore_plan_id')
            context_extra['restore_duration_months'] = request.session.get('restore_duration_months')
            context_extra['restore_user_scope'] = request.session.get('restore_user_scope')
            context_extra['restore_selected_users'] = request.session.get('restore_selected_users', [])
    
    plans = SubscriptionType.objects.filter(is_active=True)
    context = {
        'form': form,
        'plans': plans,
        'is_create': True,
        'no_of_tenant_users': no_of_tenant_users,

        'restoring': request.session.get('restoring_subscription', False),
        'restore_plan_id': request.session.get('restore_plan_id'),
        'restore_duration_months': request.session.get('restore_duration_months'),
        'restore_user_scope': request.session.get('restore_user_scope'),
        'restore_selected_users': request.session.get('restore_selected_users', []),
            }
    
    # Add restoration data to context if available
    if request.session.get('restoring_subscription'):
        context['restoring'] = True
        context['restore_plan_id'] = request.session.get('restore_plan_id')
        context['restore_duration_months'] = request.session.get('restore_duration_months')
        context['restore_user_scope'] = request.session.get('restore_user_scope')
        context['restore_selected_users'] = request.session.get('restore_selected_users', [])
    
    return render(request, 'subscriptions/subscription_form.html', context)

@login_required
def clear_subscription_restore_flag(request):
    """Clear the subscription restoration flag from session"""
    if request.method == 'POST':
        request.session.pop('restoring_subscription', None)
        request.session.pop('restore_plan_id', None)
        request.session.pop('restore_duration_months', None)
        request.session.pop('restore_user_scope', None)
        request.session.pop('restore_selected_users', None)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def subscription_covered_users(request, subscription_id):
    """
    AJAX endpoint to get covered users for a subscription
    """
    try:
        subscription = Subscription.objects.get(id=subscription_id)
    except Subscription.DoesNotExist:
        return JsonResponse({'error': 'Subscription not found'}, status=404)
    
    # Check permissions
    if not request.user.is_superuser:
        if subscription.tenant and subscription.tenant != getattr(request.user, 'tenant', None):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        if subscription.user and subscription.user != request.user:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Get covered users
    covered_users = subscription.get_covered_users()
    
    # Format user data for JSON response
    users_data = []
    CustomUser = apps.get_model('documents', 'CustomUser')
    
    for user in covered_users:
        users_data.append({
            'id': user.id,
            'email': user.email,
            'name': user.get_full_name() or None,
            'first_name': user.first_name,
            'last_name': user.last_name,
        })
    
    return JsonResponse({
        'users': users_data,
        'count': len(users_data),
        'subscription_id': subscription.id,
        'user_scope': subscription.user_scope if subscription.tenant else 'individual',
    })


@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal or u.is_superuser)
def subscription_detail(request, pk):
    """View subscription details with enhanced user information"""
    
    subscription = get_object_or_404(Subscription, pk=pk)
    
    is_allowed = False
    
    if request.user.is_superuser:
        is_allowed = True
    elif subscription.tenant and subscription.tenant == getattr(request.user, 'tenant', None):
        # User is admin of this tenant
        is_allowed = True
    elif subscription.user and subscription.user == request.user:
        # User is the individual subscriber
        is_allowed = True
    
    if not is_allowed:
        messages.error(request, "You don't have permission to view this subscription")
        return redirect('client_subscriptions')
    
    # Get covered users if this is a tenant subscription
    covered_users = None
    if subscription.tenant:
        covered_users = subscription.get_covered_users()
        
        # For selected scope, show the specific users
        if subscription.user_scope == 'selected':
            covered_users = subscription.covered_users.all()
        elif subscription.user_scope == 'all':
            covered_users = CustomUser.objects.filter(
                tenant=subscription.tenant,
                is_superuser=False
            )
    
    # Get related payments
    try:
        payments = subscription.payments.all().order_by('-created_at')[:10]
    except AttributeError:
        payments = []
        logger.warning(f"Payments relation not found for subscription {subscription.id}")
    
    # Get available credits
    remaining_credits = Credit.objects.filter(
        tenant=subscription.tenant,
        remaining_amount__gt=0
    ) if subscription.tenant else []
    
    # Get user count info
    user_count_info = {
        'current_count': subscription.current_user_count,
        'next_count': subscription.next_billing_user_count,
        'max_allowed': subscription.plan.max_users if subscription.plan.max_users else 'Unlimited',
        'last_updated': subscription.last_user_count_updated_at
    }
    
    context = {
        'subscription': subscription,
        'payments': payments,
        'credits': remaining_credits,
        'covered_users': covered_users,
        'user_count_info': user_count_info,
        'is_tenant_subscription': subscription.tenant is not None,
        'user_scope_display': subscription.get_user_scope_display() if subscription.tenant else None,
    }
    return render(request, 'subscriptions/subscription_detail.html', context)

@login_required
@require_POST
@user_passes_test(lambda u: is_admin(u) or u.is_personal or u.is_superuser)
def cancel_subscription(request, pk):
    """Cancel a subscription"""

    subscription = get_object_or_404(Subscription, pk=pk)

    # Superusers can cancel anything.
    # Tenant admins can only cancel subscriptions within their tenant.
    # Personal users can only cancel their own subscription.
    if request.user.is_superuser:
        pass
    elif is_admin(request.user):
        if subscription.tenant != getattr(request.user, 'tenant', None):
            return JsonResponse({'error': 'Permission denied'}, status=403)
    elif request.user.is_personal:
        if subscription.user != request.user:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    else:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        with transaction.atomic():
            subscription.status = 'cancelled'
            subscription.cancelled_at = timezone.now()
            subscription.auto_renew = False
            subscription.save()

            for user in subscription.covered_users.all():
                user.subscription_status = 'inactive'
                # user.subscription_end_date = timezone.now().date()
                user.subscription_plan = None
                user.save()

            logger.info(f"Subscription {subscription.id} cancelled by {request.user.email}")

            return JsonResponse({'success': True, 'message': 'Subscription cancelled successfully'})
    except Exception as e:
        logger.error(f"Error cancelling subscription {subscription.id}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal or u.is_superuser)
def client_subscription_payments(request):
    """List payments for the current user/tenant"""
    
    # Get base queryset
    if hasattr(request.user, 'tenant') and request.user.tenant:
        # Tenant user - show tenant payments
        payments = Payment.objects.filter(
            content_type__model='subscription',
            object_id__in=Subscription.objects.filter(tenant=request.user.tenant).values_list('id', flat=True)
        )
    elif request.user.is_superuser:
        payments = Payment.objects.filter(
            content_type__model='subscription',
            object_id__in=Subscription.objects.values_list('id', flat=True)
        )
    else:
        # Individual user - show their payments
        payments = Payment.objects.filter(
            content_type__model='subscription',
            object_id__in=Subscription.objects.filter(user=request.user).values_list('id', flat=True)
        )
    
    # Get filter parameters
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Apply filters
    if status:
        payments = payments.filter(status=status)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            payments = payments.filter(created_at__date__gte=from_date)
        except (ValueError, TypeError):
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            payments = payments.filter(created_at__date__lte=to_date)
        except (ValueError, TypeError):
            pass
    
    # Calculate stats
    total_payments = payments.count()
    successful_payments = payments.filter(status='success').count()
    failed_payments = payments.filter(status='failed').count()
    pending_payments = payments.filter(status='pending').count()
    abandoned_payments = payments.filter(status='abandoned').count()
    refunded_payments = payments.filter(status='refunded').count()
    
    # Calculate total amount
    total_amount = payments.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Pagination
    paginator = Paginator(payments.order_by('-created_at'), 10)
    page = request.GET.get('page')
    payments = paginator.get_page(page)
    
    context = {
        'payments': payments,
        'status_filter': status,
        'date_from': date_from,
        'date_to': date_to,
        'total_payments': total_payments,
        'successful_payments': successful_payments,
        'failed_payments': failed_payments,
        'pending_payments': pending_payments,
        'abandoned_payments': abandoned_payments,
        'refunded_payments': refunded_payments,
        'total_amount': total_amount,
    }
    return render(request, 'subscriptions/payments.html', context)

@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal or u.is_superuser)
def subscription_payment_detail(request, pk):
    """View payment details"""
    
    payment = get_object_or_404(Payment, pk=pk)
    
    # Check permissions
    subscription = payment.content_object
    if not (request.user.is_superuser) or (subscription.tenant and subscription.tenant != getattr(request.user, 'tenant', None)):
        messages.error(request, "You don't have permission to view this payment")
        return redirect('client_subscription_payments')
    if not (request.user.is_superuser) or (subscription.user and subscription.user != request.user):
        messages.error(request, "You don't have permission to view this payment")
        return redirect('client_subscription_payments')
    
    context = {
        'payment': payment,
    }
    return render(request, 'subscriptions/payment_detail.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_paid_subscriptions(request):
    """Admin view to manage PAID subscriptions with user scope information"""
    
    from django.db.models import Q, Sum, Count
    from django.utils import timezone
    from datetime import datetime, timedelta
    from decimal import Decimal
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    today = timezone.now().date()
    
    # Get active tab
    active_tab = request.GET.get('tab', 'active')
    
    # Get search queries for different tabs
    search_active_query = request.GET.get('search_active', '').strip()
    search_pending_query = request.GET.get('search_pending', '').strip()
    search_expired_query = request.GET.get('search_expired', '').strip()
    search_cancelled_query = request.GET.get('search_cancelled', '').strip()
    
    # Get date filters
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    
    # Pagination parameters
    page_size = 20
    active_page = request.GET.get('active_page', 1)
    pending_page = request.GET.get('pending_page', 1)
    trial_page = request.GET.get('trial_page', 1)
    expiring_page = request.GET.get('expiring_page', 1)
    expired_page = request.GET.get('expired_page', 1)
    cancelled_page = request.GET.get('cancelled_page', 1)
    
    # Get all paid subscriptions (is_free=False)
    all_paid_subs = Subscription.objects.filter(is_free=False).select_related(
        'tenant', 'user', 'plan', 'promo', 'created_by'
    ).prefetch_related('covered_users').order_by('-created_at')
    
    # Calculate total revenue from paid subscriptions
    total_revenue = Payment.objects.filter(
        payment_type='subscription',
        status='success',
        amount__gt=0
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Revenue this month
    month_start = today.replace(day=1)
    month_revenue = Payment.objects.filter(
        payment_type='subscription',
        status='success',
        amount__gt=0,
        created_at__date__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Active paid subscriptions with user scope info
    active_paid_base = all_paid_subs.filter(
        status='active',
        end_date__gte=today
    )
    
    # Annotate with covered user count for active subscriptions
    for sub in active_paid_base:
        sub.covered_user_count = sub.get_covered_user_count()
    
    # Pending payment subscriptions
    pending_paid_base = all_paid_subs.filter(
        status='pending',
        trial_end_date__isnull=True
    )
    
    # Trial subscriptions
    trial_paid_base = all_paid_subs.filter(
        status='pending',
        trial_end_date__isnull=False,
        trial_end_date__gte=today
    )
    
    # Expired subscriptions
    expired_paid_base = all_paid_subs.filter(
        Q(status='expired') | 
        Q(status='active', end_date__lt=today)
    ).order_by('-end_date')
    
    # Cancelled/Revoked subscriptions
    cancelled_paid_base = all_paid_subs.filter(
        Q(status='cancelled') | Q(status='revoked')
    ).order_by('-updated_at')
    
    # Subscriptions expiring soon
    expiring_soon_base = active_paid_base.filter(
        end_date__gte=today,
        end_date__lte=today + timedelta(days=14)
    ).order_by('end_date')
    
    # Apply search filters with user scope support
    if search_active_query:
        active_paid_base = active_paid_base.filter(
            Q(tenant__name__icontains=search_active_query) |
            Q(tenant__admin__email__icontains=search_active_query) |
            Q(user__email__icontains=search_active_query) |
            Q(user__first_name__icontains=search_active_query) |
            Q(user__last_name__icontains=search_active_query) |
            Q(plan__name__icontains=search_active_query) |
            Q(promo_code__icontains=search_active_query) |
            Q(user_scope__icontains=search_active_query)  # Search by user scope
        )
        expiring_soon_base = expiring_soon_base.filter(
            Q(tenant__name__icontains=search_active_query) |
            Q(tenant__admin__email__icontains=search_active_query) |
            Q(user__email__icontains=search_active_query) |
            Q(user__first_name__icontains=search_active_query) |
            Q(user__last_name__icontains=search_active_query) |
            Q(plan__name__icontains=search_active_query) |
            Q(promo_code__icontains=search_active_query) |
            Q(user_scope__icontains=search_active_query)
        )
    
    if search_pending_query:
        pending_paid_base = pending_paid_base.filter(
            Q(tenant__name__icontains=search_pending_query) |
            Q(tenant__admin__email__icontains=search_pending_query) |
            Q(user__email__icontains=search_pending_query) |
            Q(user__first_name__icontains=search_pending_query) |
            Q(user__last_name__icontains=search_pending_query) |
            Q(plan__name__icontains=search_pending_query) |
            Q(promo_code__icontains=search_pending_query) |
            Q(user_scope__icontains=search_pending_query)
        )
        trial_paid_base = trial_paid_base.filter(
            Q(tenant__name__icontains=search_pending_query) |
            Q(tenant__admin__email__icontains=search_pending_query) |
            Q(user__email__icontains=search_pending_query) |
            Q(user__first_name__icontains=search_pending_query) |
            Q(user__last_name__icontains=search_pending_query) |
            Q(plan__name__icontains=search_pending_query) |
            Q(promo_code__icontains=search_pending_query) |
            Q(user_scope__icontains=search_pending_query)
        )
    
    # Create paginators
    active_paginator = Paginator(active_paid_base, page_size)
    pending_paginator = Paginator(pending_paid_base, page_size)
    trial_paginator = Paginator(trial_paid_base, page_size)
    expiring_paginator = Paginator(expiring_soon_base, page_size)
    expired_paginator = Paginator(expired_paid_base, page_size)
    cancelled_paginator = Paginator(cancelled_paid_base, page_size)
    
    # Get current pages
    try:
        active_paid_subs = active_paginator.page(active_page)
    except (PageNotAnInteger, EmptyPage):
        active_paid_subs = active_paginator.page(1)
    
    try:
        pending_paid_subs = pending_paginator.page(pending_page)
    except (PageNotAnInteger, EmptyPage):
        pending_paid_subs = pending_paginator.page(1)
    
    try:
        trial_paid_subs = trial_paginator.page(trial_page)
    except (PageNotAnInteger, EmptyPage):
        trial_paid_subs = trial_paginator.page(1)
    
    try:
        expiring_soon = expiring_paginator.page(expiring_page)
    except (PageNotAnInteger, EmptyPage):
        expiring_soon = expiring_paginator.page(1)
    
    try:
        expired_paid_subs = expired_paginator.page(expired_page)
    except (PageNotAnInteger, EmptyPage):
        expired_paid_subs = expired_paginator.page(1)
    
    try:
        cancelled_paid_subs = cancelled_paginator.page(cancelled_page)
    except (PageNotAnInteger, EmptyPage):
        cancelled_paid_subs = cancelled_paginator.page(1)
    
    # Calculate additional stats
    total_users_covered = 0
    for sub in active_paid_base:
        total_users_covered += sub.get_covered_user_count()
    
    context = {
        # Stats for cards
        'total_paid_count': all_paid_subs.count(),
        'active_paid_count': active_paginator.count,
        'pending_paid_count': pending_paginator.count,
        'trial_paid_count': trial_paginator.count,
        'expired_paid_count': expired_paginator.count,
        'cancelled_paid_count': cancelled_paginator.count,
        'expiring_soon_count': expiring_paginator.count,
        'total_revenue': total_revenue,
        'month_revenue': month_revenue,
        'total_users_covered': total_users_covered,
        
        # Paginated subscription querysets
        'active_paid_subs': active_paid_subs,
        'pending_paid_subs': pending_paid_subs,
        'trial_paid_subs': trial_paid_subs,
        'expired_paid_subs': expired_paid_subs,
        'cancelled_paid_subs': cancelled_paid_subs,
        'expiring_soon': expiring_soon,
        
        # Pagination objects
        'active_page_obj': active_paid_subs,
        'pending_page_obj': pending_paid_subs,
        'trial_page_obj': trial_paid_subs,
        'expiring_page_obj': expiring_soon,
        'expired_page_obj': expired_paid_subs,
        'cancelled_page_obj': cancelled_paid_subs,
        
        # Search queries
        'search_active_query': search_active_query,
        'search_pending_query': search_pending_query,
        'search_expired_query': search_expired_query,
        'search_cancelled_query': search_cancelled_query,
        'date_from': date_from,
        'date_to': date_to,
        
        'active_tab': active_tab,
        'now': today,
        'user_scope_choices': Subscription.USER_SCOPE_CHOICES,
    }
    return render(request, 'subscriptions/admin/manage_paid_subscriptions.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def subscription_adjustments(request):
    """View all subscription adjustments (admin only)"""
    
    adjustments = Payment.objects.filter(payment_type='subscription_adjustment').order_by('-created_at')
    
    # Filter by tenant
    tenant_id = request.GET.get('tenant')
    if tenant_id:
        adjustments = adjustments.filter(
            object_id__in=Subscription.objects.filter(tenant_id=tenant_id).values_list('id', flat=True)
        )
    
    context = {
        'adjustments': adjustments[:50],  # Last 50 adjustments
    }
    return render(request, 'subscriptions/subscription_adjustments.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def apply_credit(request, subscription_id):
    """Apply credit to subscription"""
    
    subscription = get_object_or_404(Subscription, pk=subscription_id)
    
    if request.method == 'POST':
        form = CreditApplyForm(request.POST, subscription=subscription)
        if form.is_valid():
            credit = form.cleaned_data['credit']
            amount = form.cleaned_data['amount']
            
            # Apply credit
            applied = credit.apply_credit(amount)
            
            # Create payment record
            payment = Payment.objects.create(
                payment_type='credit',
                direction='outgoing',
                amount=applied,
                status='success',
                content_type=ContentType.objects.get_for_model(subscription),
                object_id=subscription.id,
                description=f"Credit applied from {credit.credit_type}",
                metadata={
                    'credit_id': credit.id,
                    'original_amount': amount
                }
            )
            
            messages.success(request, f'₦{applied} credit applied successfully!')
            return redirect('subscription_detail', pk=subscription_id)
    else:
        form = CreditApplyForm(subscription=subscription)
    
    context = {
        'form': form,
        'subscription': subscription,
    }
    return render(request, 'subscriptions/apply_credit.html', context)


@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal or u.is_superuser)
def subscription_base(request):
    """Subscription base page with enhanced user coverage info"""
    
    try:
        # Get subscription statistics for the current user/tenant
        subscription_stats = {}
        user_coverage = None
        
        if hasattr(request.user, 'tenant') and request.user.tenant:
            # Tenant user - check which subscriptions cover them
            covering_subs = Subscription.objects.filter(
                tenant=request.user.tenant,
                status='active'
            ).filter(
                models.Q(user_scope='all') | 
                models.Q(user_scope='selected', covered_users=request.user)
            ).order_by('-created_at')
            
            active_sub = covering_subs.first()
            
            if active_sub:
                # Get all users covered by this subscription
                all_covered_users = active_sub.get_covered_users()
                
                subscription_stats = {
                    'has_active': True,
                    'plan_name': active_sub.plan.name,
                    'end_date': active_sub.end_date,
                    'days_remaining': (active_sub.end_date - timezone.now().date()).days if active_sub.end_date else 0,
                    'current_users': active_sub.current_user_count,
                    'max_users': active_sub.plan.max_users,
                    'monthly_rate': active_sub.get_current_monthly_rate(),
                    'user_scope': active_sub.user_scope,
                    'covered_users_count': all_covered_users.count(),
                    'is_covered': True,
                }
                
                # Check if user is covered by this subscription
                if active_sub.user_scope == 'selected':
                    user_coverage = {
                        'is_covered': request.user in all_covered_users,
                        'coverage_type': 'selected'
                    }
                else:
                    user_coverage = {
                        'is_covered': True,
                        'coverage_type': 'all'
                    }
            else:
                # Check if there are any active subscriptions in tenant
                any_active = Subscription.objects.filter(
                    tenant=request.user.tenant,
                    status='active'
                ).exists()
                
                if any_active:
                    subscription_stats = {
                        'has_active': False,
                        'message': 'Your organization has active subscriptions, but you are not covered by any.',
                        'action_required': 'contact_admin'
                    }
                    user_coverage = {
                        'is_covered': False,
                        'message': 'You are not included in any subscription'
                    }
                else:
                    subscription_stats = {
                        'has_active': False,
                        'message': 'No active subscription'
                    }
        
        elif hasattr(request.user, 'is_personal') and request.user.is_personal:
            # Personal user - get individual subscription info
            active_sub = Subscription.objects.filter(
                user=request.user,
                status='active'
            ).first()
            
            if active_sub:
                subscription_stats = {
                    'has_active': True,
                    'plan_name': active_sub.plan.name,
                    'end_date': active_sub.end_date,
                    'days_remaining': (active_sub.end_date - timezone.now().date()).days if active_sub.end_date else 0,
                    'monthly_rate': active_sub.get_current_monthly_rate(),
                    'is_free': active_sub.is_free,
                }
            else:
                subscription_stats = {
                    'has_active': False,
                    'message': 'No active subscription'
                }
        
        context = {
            'subscription_stats': subscription_stats,
            'user_coverage': user_coverage,
            'active_tab': request.GET.get('tab', 'overview'),
            'is_tenant_user': hasattr(request.user, 'tenant') and request.user.tenant,
            'is_personal_user': hasattr(request.user, 'is_personal') and request.user.is_personal,
        }
        
        return render(request, 'subscriptions/base_subscription.html', context)
        
    except Exception as e:
        logger.error(f"Error in subscription_base view: {str(e)}")
        messages.error(request, "An error occurred loading subscription page")
        return render(request, 'subscriptions/base_subscription.html', {'error': str(e)})
    


def get_user_subscription_summary(user):
    """
    Helper function to get a summary of user's subscription status
    Returns a dict with comprehensive subscription info
    """
    summary = {
        'has_access': False,
        'subscription_type': None,
        'subscription_id': None,
        'plan_name': None,
        'end_date': None,
        'days_remaining': None,
        'is_free': False,
        'covered_by': None,
        'warnings': []
    }
    
    today = timezone.now().date()
    
    # Check individual subscription
    individual_sub = Subscription.objects.filter(
        user=user,
        status='active'
    ).first()
    
    if individual_sub:
        summary.update({
            'has_access': True,
            'subscription_type': 'individual',
            'subscription_id': individual_sub.id,
            'plan_name': individual_sub.plan.name,
            'end_date': individual_sub.end_date,
            'days_remaining': (individual_sub.end_date - today).days if individual_sub.end_date else None,
            'is_free': individual_sub.is_free,
            'covered_by': 'individual'
        })
        
        # Add warnings if subscription is ending soon
        if summary['days_remaining'] and summary['days_remaining'] <= 7:
            summary['warnings'].append({
                'type': 'expiring_soon',
                'message': f'Your subscription ends in {summary["days_remaining"]} days'
            })
        
        return summary
    
    # Check tenant coverage
    if hasattr(user, 'tenant') and user.tenant:
        covering_subs = Subscription.objects.filter(
            tenant=user.tenant,
            status='active'
        ).filter(
            models.Q(user_scope='all') | 
            models.Q(user_scope='selected', covered_users=user)
        ).order_by('-created_at')
        
        active_sub = covering_subs.first()
        
        if active_sub:
            summary.update({
                'has_access': True,
                'subscription_type': f'tenant_{active_sub.user_scope}',
                'subscription_id': active_sub.id,
                'plan_name': active_sub.plan.name,
                'end_date': active_sub.end_date,
                'days_remaining': (active_sub.end_date - today).days if active_sub.end_date else None,
                'is_free': active_sub.is_free,
                'covered_by': 'tenant',
                'user_scope': active_sub.user_scope
            })
            
            # Add warnings if subscription is ending soon
            if summary['days_remaining'] and summary['days_remaining'] <= 7:
                summary['warnings'].append({
                    'type': 'expiring_soon',
                    'message': f'Your organization\'s subscription ends in {summary["days_remaining"]} days'
                })
            
            # Check if user is covered in selected scope
            if active_sub.user_scope == 'selected':
                if user in active_sub.covered_users.all():
                    summary['warnings'].append({
                        'type': 'selected_coverage',
                        'message': 'You are specifically selected for this subscription'
                    })
    
    return summary


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_free_subscriptions(request):
    """Admin view to manage free/exempt subscriptions with search and tabs"""
    
    from django.db.models import Q
    from django.utils import timezone
    from datetime import datetime
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    today = timezone.now().date()
    
    # Get active tab
    active_tab = request.GET.get('tab', 'grant')
    
    # Get search queries for different tabs
    search_query = request.GET.get('search', '').strip()
    search_active_query = request.GET.get('search_active', '').strip()
    search_expired_query = request.GET.get('search_expired', '').strip()
    search_past_query = request.GET.get('search_past', '').strip()
    
    # Get date filters for expired tab
    expired_from = request.GET.get('expired_from', '').strip()
    expired_to = request.GET.get('expired_to', '').strip()
    
    # Pagination parameters
    page_size = 20  # Number of items per page
    active_page = request.GET.get('active_page', 1)
    expired_page = request.GET.get('expired_page', 1)
    past_page = request.GET.get('past_page', 1)
    
    # Get all tenants and personal users for granting access (Tab 1)
    tenants = Tenant.objects.all()
    users = CustomUser.objects.filter(is_personal=True, tenant__isnull=True)
    
    # Apply search to tenants and users if query exists
    if search_query:
        tenants = tenants.filter(
            Q(name__icontains=search_query) | 
            Q(slug__icontains=search_query) |
            Q(admin__email__icontains=search_query)
        )
        users = users.filter(
            Q(email__icontains=search_query) | 
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query)
        )
    
    # Get all free subscriptions with related data
    all_free_subs = Subscription.objects.filter(is_free=True).select_related(
        'tenant', 'user', 'plan', 'free_approved_by'
    ).order_by('-created_at')
    
    # Active subscriptions
    free_subs_active_base = all_free_subs.filter(
        ~Q(status='revoked'),
        ~Q(status='expired'),
        ~Q(status='cancelled'),
        Q(free_expires_at__isnull=True) | Q(free_expires_at__gte=today)
    )
    
    # Past subscriptions
    free_subs_past_base = all_free_subs.filter(
        Q(status='revoked') | Q(status='expired') | Q(status='cancelled')
    ).order_by('-updated_at')
    
    # Expired subscriptions
    free_subs_expired_base = all_free_subs.filter(
        free_expires_at__isnull=False, 
        free_expires_at__lt=today + timezone.timedelta(days=1)
    )
    
    # Apply search filters to base querysets
    if search_active_query:
        free_subs_active_base = free_subs_active_base.filter(
            Q(tenant__name__icontains=search_active_query) |
            Q(tenant__admin__email__icontains=search_active_query) |
            Q(user__email__icontains=search_active_query) |
            Q(user__first_name__icontains=search_active_query) |
            Q(user__last_name__icontains=search_active_query) |
            Q(free_reason__icontains=search_active_query) |
            Q(plan__name__icontains=search_active_query)
        )
    
    if search_expired_query:
        free_subs_expired_base = free_subs_expired_base.filter(
            Q(tenant__name__icontains=search_expired_query) |
            Q(tenant__admin__email__icontains=search_expired_query) |
            Q(user__email__icontains=search_expired_query) |
            Q(user__first_name__icontains=search_expired_query) |
            Q(user__last_name__icontains=search_expired_query) |
            Q(free_reason__icontains=search_expired_query) |
            Q(plan__name__icontains=search_expired_query)
        )
    
    if search_past_query:
        free_subs_past_base = free_subs_past_base.filter(
            Q(tenant__name__icontains=search_past_query) |
            Q(tenant__admin__email__icontains=search_past_query) |
            Q(user__email__icontains=search_past_query) |
            Q(user__first_name__icontains=search_past_query) |
            Q(user__last_name__icontains=search_past_query) |
            Q(free_reason__icontains=search_past_query) |
            Q(plan__name__icontains=search_past_query)
        )
    
    # Apply date filters to expired
    if expired_from:
        try:
            from_date = datetime.strptime(expired_from, '%Y-%m-%d').date()
            free_subs_expired_base = free_subs_expired_base.filter(free_expires_at__gte=from_date)
        except (ValueError, TypeError):
            pass
    
    if expired_to:
        try:
            to_date = datetime.strptime(expired_to, '%Y-%m-%d').date()
            free_subs_expired_base = free_subs_expired_base.filter(free_expires_at__lte=to_date + timezone.timedelta(days=1))
        except (ValueError, TypeError):
            pass
    
    # Create paginators
    active_paginator = Paginator(free_subs_active_base, page_size)
    expired_paginator = Paginator(free_subs_expired_base, page_size)
    past_paginator = Paginator(free_subs_past_base, page_size)
    
    # Get current pages
    try:
        free_subs_active = active_paginator.page(active_page)
    except (PageNotAnInteger, EmptyPage):
        free_subs_active = active_paginator.page(1)
    
    try:
        free_subs_expired = expired_paginator.page(expired_page)
    except (PageNotAnInteger, EmptyPage):
        free_subs_expired = expired_paginator.page(1)
    
    try:
        free_subs_past = past_paginator.page(past_page)
    except (PageNotAnInteger, EmptyPage):
        free_subs_past = past_paginator.page(1)
    
    context = {
        'tenants': tenants,
        'users': users,
        'free_subs_active': free_subs_active,
        'free_subs_expired': free_subs_expired,
        'free_subs_past': free_subs_past,
        'active_subs_count': active_paginator.count,
        'expired_subs_count': expired_paginator.count,
        'past_subs_count': past_paginator.count,
        'search_query': search_query,
        'search_active_query': search_active_query,
        'search_expired_query': search_expired_query,
        'search_past_query': search_past_query,
        'expired_from': expired_from,
        'expired_to': expired_to,
        'active_tab': active_tab,
        'now': today,
        # Pagination info
        'active_page_obj': free_subs_active,
        'expired_page_obj': free_subs_expired,
        'past_page_obj': free_subs_past,
    }
    return render(request, 'subscriptions/admin/manage_free.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def search_clients_for_free_access(request):
    """JSON endpoint for live search of tenants and personal users"""
    
    search_query = request.GET.get('q', '').strip()
    client_type = request.GET.get('type', 'all')  # 'tenant', 'user', or 'all'
    
    results = []
    
    if not search_query or len(search_query) < 2:
        return JsonResponse({'results': results})
    
    if client_type in ['all', 'tenant']:
        # Search tenants
        tenants = Tenant.objects.filter(
            Q(name__icontains=search_query) | 
            Q(slug__icontains=search_query) |
            Q(admin__email__icontains=search_query)
        )[:10]  # Limit to 10 results
        
        for tenant in tenants:
            results.append({
                'id': f"tenant_{tenant.id}",
                'text': f"{tenant.name} ({tenant.admin.email if tenant.admin else 'N/A'})",
                'type': 'tenant',
                'original_id': tenant.id
            })
    
    if client_type in ['all', 'user']:
        # Search personal users
        users = CustomUser.objects.filter(
            is_personal=True, 
            tenant__isnull=True
        ).filter(
            Q(email__icontains=search_query) | 
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query)
        )[:10]
        
        for user in users:
            results.append({
                'id': f"user_{user.id}",
                'text': f"{user.email}",
                'type': 'user',
                'original_id': user.id
            })
    
    return JsonResponse({'results': results})

@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def extend_free_access(request):
    """Extend free access for a subscription"""
    subscription_id = request.POST.get('subscription_id')
    days = request.POST.get('days')
    
    try:
        subscription = Subscription.objects.get(id=subscription_id, is_free=True)
        
        if subscription.free_expires_at:
            subscription.free_expires_at += timedelta(days=int(days))
        else:
            subscription.free_expires_at = timezone.now().date() + timedelta(days=int(days))
        
        subscription.save()
        
        logger.info(f"Free access extended for subscription {subscription_id} by {days} days")
        return JsonResponse({'success': True})
        
    except Subscription.DoesNotExist:
        return JsonResponse({'error': 'Subscription not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def grant_free_access(request):
    """Grant free access to a user/tenant"""
    from django.utils import timezone
    from datetime import datetime, timedelta
    
    user_id = request.POST.get('user_id')
    tenant_id = request.POST.get('tenant_id')
    reason = request.POST.get('reason')
    expires_at = request.POST.get('expires_at')
    redirect_tab = request.POST.get('redirect_tab', 'active')
    
    # Validate that either tenant_id or user_id is provided
    if not tenant_id and not user_id:
        messages.error(request, 'Please select a tenant or user')
        return redirect('manage_free_subscriptions')
    
    # Validate reason
    if not reason:
        messages.error(request, 'Please provide a reason for free access')
        return redirect('manage_free_subscriptions')
    
    try:
        with transaction.atomic():
            # Get the default active plan
            default_plan = SubscriptionType.objects.filter(is_active=True).first()
            if not default_plan:
                messages.error(request, 'No active subscription plan found. Please create a plan first.')
                return redirect('manage_free_subscriptions')
            
            # Calculate expiration date
            expiration_date = None
            if expires_at and expires_at.strip():
                # Use the date provided by the user
                try:
                    expiration_date = datetime.strptime(expires_at, '%Y-%m-%d').date()
                except ValueError:
                    messages.error(request, 'Invalid date format. Please use YYYY-MM-DD.')
                    return redirect('manage_free_subscriptions')
            else:
                # Default to 30 days from now
                expiration_date = timezone.now().date() + timedelta(days=30)
            
            # Current date for start_date
            start_date = timezone.now().date()
            
            if tenant_id:
                tenant = Tenant.objects.get(id=tenant_id)
                
                # Check if there's already an active free subscription for this tenant
                existing_sub = Subscription.objects.filter(
                    tenant=tenant,
                    is_free=True,
                    status='active',
                    end_date__lte=timezone.now(),
                    free_expires_at__lte=timezone.now(),
                ).first()
                
                if existing_sub:
                    # Update existing subscription
                    sub = existing_sub
                    sub.free_reason = reason
                    sub.free_approved_by = request.user
                    sub.free_approved_at = timezone.now()
                    sub.free_expires_at = expiration_date
                    sub.end_date = expiration_date  # Also update end_date
                    sub.status = 'active'
                    sub.updated_at = timezone.now()
                    sub.save()
                    created = False
                else:
                    # Create new subscription with proper dates
                    sub = Subscription(
                        tenant=tenant,
                        plan=default_plan,
                        status='active',
                        start_date=start_date,
                        end_date=expiration_date,
                        is_free=True,
                        free_reason=reason,
                        free_approved_by=request.user,
                        free_approved_at=timezone.now(),
                        free_expires_at=expiration_date
                    )
                    sub.save()
                    created = True
                
                logger.info(f"{'Created' if created else 'Updated'} free subscription for tenant {tenant.name}")
                
            elif user_id:
                user = CustomUser.objects.get(id=user_id)
                
                # Check if there's already an active free subscription for this user
                existing_sub = Subscription.objects.filter(
                    user=user,
                    is_free=True,
                    status='active',
                    end_date__lte=timezone.now(),
                    free_expires_at__lte=timezone.now(),
                ).first()
                
                if existing_sub:
                    # Update existing subscription
                    sub = existing_sub
                    sub.free_reason = reason
                    sub.free_approved_by = request.user
                    sub.free_approved_at = timezone.now()
                    sub.free_expires_at = expiration_date
                    sub.end_date = expiration_date  # Also update end_date
                    sub.status = 'active'
                    sub.updated_at = timezone.now()
                    sub.save()
                    created = False
                else:
                    # Create new subscription with proper dates
                    sub = Subscription(
                        user=user,
                        plan=default_plan,
                        status='active',
                        start_date=start_date,
                        end_date=expiration_date,
                        is_free=True,
                        free_reason=reason,
                        free_approved_by=request.user,
                        free_approved_at=timezone.now(),
                        free_expires_at=expiration_date
                    )
                    sub.save()
                    created = True
                
                logger.info(f"{'Created' if created else 'Updated'} free subscription for user {user.email}")
            
            # Add success message with expiration info
            messages.success(
                request, 
                f'Free access {"updated" if not created else "granted"} successfully for {"tenant" if tenant_id else "user"}! Expires on {expiration_date.strftime("%Y-%m-%d")}.'
            )
            
            # Redirect to the active tab
            return redirect(f"{reverse('manage_free_subscriptions')}?tab={redirect_tab}")
            
    except Tenant.DoesNotExist:
        messages.error(request, 'Selected tenant not found')
        return redirect('manage_free_subscriptions')
    except CustomUser.DoesNotExist:
        messages.error(request, 'Selected user not found')
        return redirect('manage_free_subscriptions')
    except Exception as e:
        logger.exception(f"Error granting free access: {str(e)}")
        messages.error(request, f'Error granting free access: {str(e)}')
        return redirect('manage_free_subscriptions')

@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def revoke_free_access(request):
    """Revoke free access from a subscription"""
    from django.utils import timezone
    from django.db.models import Q
    
    subscription_id = request.POST.get('subscription_id')
    
    if not subscription_id:
        return JsonResponse({'error': 'Subscription ID required'}, status=400)
    
    try:
        with transaction.atomic():
            subscription = get_object_or_404(Subscription, id=subscription_id)
            
            # Store info for logging
            subscriber = subscription.tenant or subscription.user
            subscriber_type = 'tenant' if subscription.tenant else 'user'
            
            # Revoke free access - set to revoked status
            # subscription.free_reason = None
            subscription.free_reason = 'revoked'
            subscription.free_approved_by = request.user
            # subscription.free_approved_at = None
            # subscription.free_expires_at = None
            
            # Set status to revoked
            subscription.status = 'revoked'
            subscription.end_date = timezone.now().date()
            
            # If it was a trial, also end the trial
            # if subscription.is_trial:
            #     # subscription.is_trial = False
            #     subscription.trial_end_date = timezone.now().date()
            
            subscription.save()

            for user in subscription.covered_users.all():
                user.subscription_status = 'inactive'
                # user.subscription_end_date = timezone.now().date()
                user.subscription_plan = None
                user.save()
            
            # Log the action
            logger.info(
                f"Free access revoked for {subscriber_type} {subscriber} "
                f"by admin {request.user.email}"
            )
            
            messages.success(request, f'Free access revoked successfully for {subscriber}')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            else:
                return redirect('manage_free_subscriptions')
                
    except Subscription.DoesNotExist:
        error_msg = 'Subscription not found'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': error_msg}, status=404)
        else:
            messages.error(request, error_msg)
            return redirect('manage_free_subscriptions')
            
    except Exception as e:
        logger.error(f"Error revoking free access: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': str(e)}, status=500)
        else:
            messages.error(request, f'Error revoking free access: {str(e)}')
            return redirect('manage_free_subscriptions')


@login_required
def subscription_payment_breakdown(request, subscription_id):
    """Show payment breakdown and initialize Paystack payment for subscription"""
    
    subscription = get_object_or_404(
        Subscription,
        id=subscription_id,
        status='pending',
    )
    
    # Check permissions
    if subscription.tenant and subscription.tenant != getattr(request.user, 'tenant', None):
        messages.error(request, "You don't have permission to view this subscription")
        return redirect('client_subscriptions')
    
    if subscription.user and subscription.user != request.user:
        messages.error(request, "You don't have permission to view this subscription")
        return redirect('client_subscriptions')
    
    # Clean up abandoned payments - keep only the most recent pending payment
    from django.contrib.contenttypes.models import ContentType
    
    # Get all pending payments for this subscription
    existing_payments = Payment.objects.filter(
        content_type=ContentType.objects.get_for_model(subscription),
        object_id=subscription.id,
        status='pending'
    ).order_by('-created_at')
    
    # If there are multiple pending payments, abandon all but the most recent
    if existing_payments.count() > 1:
        # Keep the newest, abandon others
        newest = existing_payments.first()
        abandoned = existing_payments.exclude(id=newest.id)
        
        for payment in abandoned:
            payment.status = 'abandoned'
            payment.metadata = payment.metadata or {}
            payment.metadata['abandoned_reason'] = 'newer_payment_initiated'
            payment.metadata['abandoned_at'] = timezone.now().isoformat()
            payment.metadata['abandoned_by'] = 'system_cleanup'
            payment.save()
        
        logger.info(f"Cleaned up {abandoned.count()} abandoned payments for subscription {subscription.id}")

    initial_price = subscription.plan.price
    monthly_price = subscription.plan.get_effective_price()
    covered_user_count = subscription.get_covered_user_count()
    print("xxx44555")
    print(monthly_price)
    # Calculate total based on duration in months
    duration_months = subscription.duration_months or 1
    total_base = monthly_price * covered_user_count * duration_months
    initial_base = initial_price * covered_user_count * duration_months

    
    # Get plan discount percentage (from the plan, not duration-based)
    plan_discount_percent = subscription.plan.discount_percentage or 0
    plan_discount_amount = initial_base * (Decimal(plan_discount_percent) / Decimal('100'))
    
    # Apply plan discount
    after_plan_discount = total_base - plan_discount_amount
    
    # Apply promo code discount if any
    promo_discount_amount = Decimal('0.00')
    
    if subscription.promo:
        if subscription.promo.discount_type == 'fixed':
            promo_discount_amount = subscription.promo.apply_discount(after_plan_discount)
            promo_discount_amount = after_plan_discount - promo_discount_amount
        elif subscription.promo.discount_type == 'percentage':
            promo_discount_amount = after_plan_discount * (Decimal(subscription.promo.discount_value) / Decimal('100'))
        elif subscription.promo.discount_type == 'full':
            promo_discount_amount = after_plan_discount
    
    # Calculate final payable amount
    payable_amount = total_base #after_plan_discount - promo_discount_amount
    
    # Ensure no negative amount
    if payable_amount < 0:
        payable_amount = Decimal('0.00')
    
    # Calculate platform fees
    percent_fee = payable_amount * (Decimal('3.5') / Decimal('100'))
    fixed_fee = Decimal('100.00')
    total_fees = percent_fee + fixed_fee
    
    # Calculate monthly equivalent
    monthly_equivalent = payable_amount / Decimal(duration_months) if duration_months > 0 else Decimal('0.00')
    
    # Calculate total savings compared to no discount
    total_savings = plan_discount_amount + promo_discount_amount
    # savings_percentage = (total_savings / total_base * 100) if total_base > 0 else 0
    # print("ddfgggg")
    # print(savings_percentage)
    
    # Get existing subscription info for display
    existing_sub = None
    today = timezone.now().date()
    
    if subscription.tenant:
        existing_sub = Subscription.objects.filter(
            tenant=subscription.tenant,
            status='active',
            end_date__gte=today
        ).order_by('-end_date').first()
    elif subscription.user:
        existing_sub = Subscription.objects.filter(
            user=subscription.user,
            status='active',
            end_date__gte=today
        ).order_by('-end_date').first()
    
    context = {
        'subscription': subscription,
        'monthly_price': monthly_price,
        'total_base': total_base,
        "initial_base": initial_base,
        'duration_months': duration_months,
        'plan_discount_percent': plan_discount_percent,  # Changed from duration_discount_percent
        'plan_discount_amount': plan_discount_amount,    # Changed from duration_discount_amount
        'promo_discount_amount': promo_discount_amount,
        'payable_amount': payable_amount,
        'total_fees': total_fees,
        'percent_fee_amount': percent_fee,
        'fixed_fee': fixed_fee,
        'monthly_equivalent': monthly_equivalent,
        'total_savings': total_savings,
        # 'savings_percentage': savings_percentage,
        'currency': 'NGN',
        'is_tenant': subscription.tenant is not None,
        'user_count': covered_user_count,
        'user_scope_display': subscription.get_user_scope_display() if subscription.tenant else None,
        'existing_sub': existing_sub,
        'is_sequential': existing_sub and existing_sub.end_date and existing_sub.end_date > today,
    }
    
    
    if request.method == "POST":
        # Check if there's already a pending payment for this subscription
        existing_pending = Payment.objects.filter(
            content_type=ContentType.objects.get_for_model(subscription),
            object_id=subscription.id,
            status='pending'
        ).first()
        
        if existing_pending:
            # If payment is less than 30 minutes old, reuse it
            time_diff = timezone.now() - existing_pending.created_at
            if time_diff.total_seconds() < 1800:  # 30 minutes
                messages.info(request, "You already have a pending payment. Continuing with existing payment...")
                # Get the authorization URL from metadata if available
                if existing_pending.metadata and 'authorization_url' in existing_pending.metadata:
                    return redirect(existing_pending.metadata['authorization_url'])
            
            # Otherwise, abandon the old one
            existing_pending.status = 'abandoned'
            existing_pending.metadata = existing_pending.metadata or {}
            existing_pending.metadata['abandoned_reason'] = 'new_payment_initiated'
            existing_pending.metadata['abandoned_at'] = timezone.now().isoformat()
            existing_pending.save()
        
        # Prepare metadata for Paystack with enhanced information
        metadata = {
            "source": "subscription",
            "source_id": str(subscription.id),
            "source_url": request.build_absolute_uri(
                reverse("subscription_detail", kwargs={"pk": subscription.id})
            ),
            "subscription_id": str(subscription.id),
            "plan_name": subscription.plan.name,
            "subscriber_email": subscription.user.email if subscription.user else subscription.tenant.admin.email if subscription.tenant and subscription.tenant.admin else request.user.email,
            "subscriber_type": "tenant" if subscription.tenant else "user",
            "monthly_price": str(monthly_price),
            "payable_amount": str(payable_amount),
            "duration_months": str(duration_months),
            "user_count": str(covered_user_count),
            "user_scope": subscription.user_scope if subscription.tenant else "individual",
            "promo_code": subscription.promo_code if subscription.promo_code else None,
            # "duration_discount_percent": str(duration_discount_percent),
            "plan_discount_percent": str(plan_discount_percent),

            "total_savings": str(total_savings),
        }
        
        # Add covered users info if applicable
        if subscription.tenant and subscription.user_scope == 'selected':
            covered_users_list = list(subscription.covered_users.values_list('id', 'email'))
            metadata['covered_users'] = str(covered_users_list)
            metadata['covered_users_count'] = str(len(covered_users_list))
        
        # Get email for payment
        if subscription.user:
            email = subscription.user.email
        elif subscription.tenant:
            # Try to get admin email first, fallback to tenant email
            if subscription.tenant.admin:
                email = subscription.tenant.admin.email
            else:
                email = subscription.tenant.email
        else:
            email = request.user.email
        
        # Initialize Paystack payment
        auth_url, reference = initialize_paystack_payment(
            email=email,
            amount_ngn=float(payable_amount),
            metadata=metadata,
        )
        
        if not auth_url or not reference:
            messages.error(request, "Payment service unavailable. Please try again.")
            return render(request, "subscriptions/subscription_payment_breakdown.html", context)
        
        request.session["subscription_success_data"]={
            "subscription_id":subscription.id,
            "payable_amount": str(payable_amount),
        }
        
        # Create payment record
        payment = Payment.objects.create(
            content_type=ContentType.objects.get_for_model(subscription),
            object_id=subscription.id,
            tenant=subscription.tenant,
            owner=subscription.user,
            payment_type="subscription",
            direction="incoming",
            amount=payable_amount,
            net_amount=payable_amount,
            status="pending",
            transaction_id=reference,
            description=f"Subscription payment: {subscription.plan.name} for {covered_user_count} user(s) - {duration_months} month(s)",
            created_by=request.user,
            # return_url=request.build_absolute_uri(
            #     reverse("subscription_detail", kwargs={"pk": subscription.id})
            # ),
            return_url=request.build_absolute_uri(
                reverse("subscription_success")
            ),
            metadata={**metadata, 'authorization_url': auth_url},
        )
        
        return redirect(auth_url)
    
    return render(request, "subscriptions/subscription_payment_breakdown.html", context)


@login_required
def subscription_success(request):
    """Show success page after subscription payment"""
    
    data = request.session.pop("subscription_success_data", None)
    
    if not data:
        return redirect("client_subscriptions")
    
    subscription_id = data["subscription_id"]
    payable_amount = Decimal(data["payable_amount"])
    
    subscription = get_object_or_404(Subscription, id=subscription_id)
    
    # Check permissions
    if subscription.tenant and subscription.tenant != getattr(request.user, 'tenant', None):
        if not request.user.is_superuser:
            messages.error(request, "You don't have permission to view this subscription")
            return redirect('client_subscriptions')
    
    if subscription.user and subscription.user != request.user:
        if not request.user.is_superuser:
            messages.error(request, "You don't have permission to view this subscription")
            return redirect('client_subscriptions')
    
    # Get covered users information for display
    covered_users_info = None
    if subscription.tenant:
        covered_users = subscription.get_covered_users()
        covered_users_info = {
            'count': covered_users.count(),
            'users': covered_users[:10],  # Show first 10 users
            'total_count': covered_users.count(),
            'scope_display': subscription.get_user_scope_display(),
        }
    
    context = {
        'subscription': subscription,
        'payable_amount': payable_amount,
        'covered_users_info': covered_users_info,
        'is_tenant': subscription.tenant is not None,
        'user_scope': subscription.user_scope if subscription.tenant else 'individual',
    }
    
    return render(request, 'subscriptions/subscription_success.html', context)

@login_required
def get_tenant_users(request):
    """AJAX endpoint to get users for a tenant"""
    tenant_id = request.GET.get('tenant_id')
    
    if not tenant_id:
        return JsonResponse({'error': 'Tenant ID required'}, status=400)
    
    try:
        tenant = Tenant.objects.get(id=tenant_id)
        
        # Check permissions
        if not request.user.is_superuser and request.user.tenant != tenant:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Get all non-superuser users in the tenant
        users = CustomUser.objects.filter(
            tenant=tenant,
            is_superuser=False
        ).values('id', 'email', 'first_name', 'last_name')
        
        # Format user data
        user_list = []
        for user in users:
            user_list.append({
                'id': user['id'],
                'email': user['email'],
                'name': f"{user['first_name']} {user['last_name']}".strip() or None
            })
        
        return JsonResponse({'users': user_list})
        
    except Tenant.DoesNotExist:
        return JsonResponse({'error': 'Tenant not found'}, status=404)

@login_required
def get_tenant_users_with_subscription(request):
    """AJAX endpoint to get tenant users with their current subscription info"""
    tenant_id = request.GET.get('tenant_id')
    search = request.GET.get('search', '').strip()
    page = int(request.GET.get('page', 1))
    page_size = 20
    
    if not tenant_id:
        return JsonResponse({'error': 'Tenant ID required'}, status=400)
    
    try:
        tenant = Tenant.objects.get(id=tenant_id)
        
        # Check permissions
        if not request.user.is_superuser and request.user.tenant != tenant:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Base queryset
        users = CustomUser.objects.filter(
            tenant=tenant,
            is_superuser=False
        ).order_by('first_name', 'last_name', 'email')
        
        # Apply search filter
        if search:
            users = users.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(username__icontains=search)
            )
        
        # Get total count for pagination
        total_count = users.count()
        total_pages = (total_count + page_size - 1) // page_size
        
        # Paginate
        users = users[(page-1)*page_size:page*page_size]
        
        # Get current date
        today = timezone.now().date()
        
        # Prepare user data with subscription info
        users_data = []
        for user in users:
            # Get the user's current subscription status
            subscription_status = {
                'has_subscription': False,
                'plan': None,
                'status': None,
                'end_date': None,
                'days_left': None,
                'is_active': False,
                'is_trial': False,
                'is_expired': False
            }
            
            # Check individual subscription first
            individual_sub = Subscription.objects.filter(
                user=user,
                status='active'
            ).first()
            
            if individual_sub:
                subscription_status.update({
                    'has_subscription': True,
                    'plan': individual_sub.plan.name,
                    'status': 'active',
                    'end_date': individual_sub.end_date,
                    'days_left': (individual_sub.end_date - today).days if individual_sub.end_date else None,
                    'is_active': True
                })
            else:
                # Check if covered by tenant subscription
                covered_sub = Subscription.objects.filter(
                    tenant=tenant,
                    status='active'
                ).filter(
                    Q(user_scope='all') | 
                    Q(user_scope='selected', covered_users=user)
                ).order_by('-created_at').first()
                
                if covered_sub:
                    days_left = (covered_sub.end_date - today).days if covered_sub.end_date else None
                    subscription_status.update({
                        'has_subscription': True,
                        'plan': covered_sub.plan.name,
                        'status': 'active' if covered_sub.status == 'active' else 'trial',
                        'end_date': covered_sub.end_date,
                        'days_left': days_left,
                        'is_active': covered_sub.status == 'active'
                    })
            
            # Check for any pending subscription
            if not subscription_status['has_subscription']:
                pending_sub = Subscription.objects.filter(
                    tenant=tenant,
                    user=user,
                    status='pending'
                ).first()
                if pending_sub:
                    subscription_status.update({
                        'has_subscription': True,
                        'plan': pending_sub.plan.name,
                        'status': 'pending',
                        'end_date': pending_sub.end_date,
                        'is_active': False
                    })
            
            users_data.append({
                'id': user.id,
                'email': user.email,
                'name': user.get_full_name() or None,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'subscription': subscription_status
            })
        
        return JsonResponse({
            'users': users_data,
            'total_count': total_count,
            'total_pages': total_pages,
            'current_page': page,
            'has_next': page < total_pages,
            'has_previous': page > 1
        })
        
    except Tenant.DoesNotExist:
        return JsonResponse({'error': 'Tenant not found'}, status=404)


# @login_required
# @require_GET
# def get_plan_price(request, plan_id):
#     """AJAX endpoint to get plan price for selected duration and users"""
#     try:
#         plan = SubscriptionType.objects.get(id=plan_id, is_active=True)
#         user_count = int(request.GET.get('users', 1))
#         duration_months = int(request.GET.get('months', 1))
        
#         monthly_price = plan.get_effective_price()
#         total_base = monthly_price * user_count * duration_months
        
#         # Calculate savings for longer durations
#         # savings = 0
#         # savings_percentage = 0
        
#         # if duration_months >= 12:
#         #     savings_percentage = 15
#         #     savings = total_base * Decimal('0.15')
#         # elif duration_months >= 6:
#         #     savings_percentage = 10
#         #     savings = total_base * Decimal('0.10')
#         # if duration_months >= 3:
#         #     savings_percentage = 5
#         #     savings = total_base * Decimal('0.05')
#         savings_percentage = plan.discount_percentage
#         savings = total_base * Decimal(str(savings_percentage / 100))
        
#         total_price = total_base - savings
        
#         return JsonResponse({
#             'monthly_price': float(monthly_price),
#             'total_base': float(total_base),
#             'total_price': float(total_price),
#             'savings': float(savings),
#             'savings_percentage': savings_percentage,
#             'user_count': user_count,
#             'duration_months': duration_months
#         })
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_GET
def get_plan_price(request, plan_id):
    """AJAX endpoint to get plan price for selected duration and users"""
    try:
        plan = SubscriptionType.objects.get(id=plan_id, is_active=True)
        user_count = int(request.GET.get('users', 1))
        duration_months = int(request.GET.get('months', 1))
        
        monthly_price = plan.get_effective_price()
        total_base = monthly_price * user_count * duration_months
        
        # Get plan's discount percentage
        plan_discount_percent = plan.discount_percentage or 0
        
        # Apply plan discount
        discount_amount = total_base * (Decimal(plan_discount_percent) / Decimal('100'))
        total_price = total_base - discount_amount
        
        return JsonResponse({
            'monthly_price': float(monthly_price),
            'total_base': float(total_base),
            'total_price': float(total_price),
            'savings': float(discount_amount),
            'savings_percentage': plan_discount_percent,
            'plan_discount_percent': plan_discount_percent,
            'user_count': user_count,
            'duration_months': duration_months
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)