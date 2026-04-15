from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
import logging
from documents.viewfuncs.rba_decorators import is_admin
from ..models import Subscription, SubscriptionType
from documents.models import Payment
from ..forms import SubscriptionTypeForm, CreditApplyForm

logger = logging.getLogger(__name__)

@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal or u.is_superuser)
def list_subscription_plans(request):
    """List all subscription plans"""
    
    plans = SubscriptionType.objects.all().order_by('-is_active', 'price')
    
    context = {
        'plans': plans,
    }
    return render(request, 'subscription_plans/subscription_plans.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_subscription_plan(request):
    """Create a new subscription plan"""
    
    if request.method == 'POST':
        form = SubscriptionTypeForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f'Plan "{plan.name}" created successfully!')
            return redirect('list_subscription_plans')
    else:
        form = SubscriptionTypeForm()
    
    context = {
        'form': form,
        'is_create': True,
    }
    return render(request, 'subscription_plans/create_plan.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_subscription_plan(request, pk):
    """Edit a subscription plan"""
    
    plan = get_object_or_404(SubscriptionType, pk=pk)
    
    if request.method == 'POST':
        form = SubscriptionTypeForm(request.POST, instance=plan)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f'Plan "{plan.name}" updated successfully!')
            return redirect('list_subscription_plans')
    else:
        form = SubscriptionTypeForm(instance=plan)
    
    context = {
        'form': form,
        'plan': plan,
        'is_create': False,
    }
    return render(request, 'subscription_plans/edit_plan.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def toggle_subscription_plan_active(request, pk):
    """Toggle plan active status"""
    
    plan = get_object_or_404(SubscriptionType, pk=pk)
    plan.is_active = not plan.is_active
    plan.save()
    
    status = 'activated' if plan.is_active else 'deactivated'
    messages.success(request, f'Plan "{plan.name}" {status} successfully!')
    
    return redirect('list_subscription_plans')



@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal)
def get_subscription_stats(request):
    """Get subscription statistics for dashboard"""
    
    if hasattr(request.user, 'tenant') and request.user.tenant:
        tenant = request.user.tenant
        active_sub = tenant.get_active_subscription()
        
        stats = {
            'has_active_subscription': active_sub is not None,
            'current_user_count': tenant.get_user_count(),
            'next_billing_date': active_sub.end_date if active_sub else None,
            'next_billing_amount': float(active_sub.get_next_monthly_rate()) if active_sub else 0,
            'status': active_sub.status if active_sub else 'none',
        }
    else:
        # Individual user
        active_sub = Subscription.objects.filter(user=request.user, status='active').first()
        
        stats = {
            'has_active_subscription': active_sub is not None,
            'plan_name': active_sub.plan.name if active_sub else None,
            'next_billing_date': active_sub.end_date if active_sub else None,
            'next_billing_amount': float(active_sub.get_next_monthly_rate()) if active_sub else 0,
            'status': active_sub.status if active_sub else 'none',
        }
    
    return JsonResponse(stats)