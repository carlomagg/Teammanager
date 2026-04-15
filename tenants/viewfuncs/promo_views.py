from django.http import JsonResponse
from ..models import Promo
from ..forms import PromoApplyForm, PromoForm
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from documents.viewfuncs.rba_decorators import is_admin
from django.views.decorators.http import require_POST


@login_required
@user_passes_test(lambda u: is_admin(u) or u.is_personal)
def validate_promo_code(request):
    """AJAX endpoint to validate promo code in real-time"""
    if request.method == 'POST':
        code = request.POST.get('promo_code')
        plan_id = request.POST.get('plan_id')
        
        from ..models import SubscriptionType
        plan = SubscriptionType.objects.filter(id=plan_id).first() if plan_id else None
        
        # Create form for validation
        form = PromoApplyForm(
            data={'promo_code': code},
            user=request.user,
            tenant=getattr(request.user, 'tenant', None),
            plan=plan
        )
        
        if form.is_valid():
            promo = form.cleaned_data['promo_code']
            return JsonResponse({
                'valid': True,
                'discount_type': promo.discount_type,
                'discount_value': float(promo.discount_value),
                'message': 'Promo code applied successfully!'
            })
        else:
            errors = form.errors.get('promo_code', ['Invalid promo code'])
            return JsonResponse({
                'valid': False,
                'message': errors[0]
            })
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def promo_list(request):
    """List all promo codes"""
    promos = Promo.objects.all().order_by('-created_at')
    
    context = {
        'promos': promos,
    }
    return render(request, 'subscriptions/admin/promo_list.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def promo_create(request):
    """Create a new promo code"""
    if request.method == 'POST':
        form = PromoForm(request.POST)
        if form.is_valid():
            promo = form.save(commit=False)
            promo.created_by = request.user
            promo.save()
            form.save_m2m()  # Save many-to-many relationships
            
            messages.success(request, f'Promo code "{promo.code}" created successfully!')
            return redirect('promo_list')
    else:
        form = PromoForm()
    
    context = {
        'form': form,
        'is_create': True,
    }
    return render(request, 'subscriptions/admin/promo_form.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def promo_edit(request, pk):
    """Edit a promo code"""
    promo = get_object_or_404(Promo, pk=pk)
    
    if request.method == 'POST':
        form = PromoForm(request.POST, instance=promo)
        if form.is_valid():
            promo = form.save()
            messages.success(request, f'Promo code "{promo.code}" updated successfully!')
            return redirect('promo_list')
    else:
        form = PromoForm(instance=promo)
    
    context = {
        'form': form,
        'promo': promo,
        'is_create': False,
    }
    return render(request, 'subscriptions/admin/promo_form.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def promo_toggle_active(request, pk):
    """Toggle promo active status"""
    promo = get_object_or_404(Promo, pk=pk)
    promo.is_active = not promo.is_active
    promo.save()
    
    status = 'activated' if promo.is_active else 'deactivated'
    messages.success(request, f'Promo code "{promo.code}" {status} successfully!')
    
    return redirect('promo_list')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def promo_stats(request, pk):
    """View promo usage statistics"""
    promo = get_object_or_404(Promo, pk=pk)
    subscriptions = promo.subscriptions.all().select_related('tenant', 'user', 'plan')
    
    total_savings = sum(
        sub.plan.price * (sub.promo_code_discount / 100) 
        for sub in subscriptions 
        if sub.promo_code_discount
    )
    
    context = {
        'promo': promo,
        'subscriptions': subscriptions,
        'total_savings': total_savings,
        'usage_percentage': (promo.uses / promo.max_uses * 100) if promo.max_uses else None,
    }
    return render(request, 'subscriptions/admin/promo_stats.html', context)