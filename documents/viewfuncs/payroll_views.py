"""
Views for payroll management.
Handles payroll creation, approval workflow, payment execution, and reporting.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from documents.models import Payroll, PayrollItem, PayrollCustomColumn, PayrollColumnTemplate, PayrollApproval, Payment, Payee, CustomUser
from documents.payroll_forms_pkg.payroll_forms import (
    PayrollForm, PayrollItemForm, PayrollCustomFieldForm,
    PayrollPasswordForm, SetPayrollPasswordForm, PayrollApprovalForm
)
from documents.utils.payroll_helpers import (
    get_user_highest_role_level, user_can_approve_payroll, user_can_pay_payroll,
    get_user_role_name, auto_fill_staff_details, get_payroll_summary,
    validate_payroll_for_approval, validate_payroll_for_payment,
    set_payroll_password, has_payroll_password, get_staff_with_profiles
)


@login_required
def payroll_dashboard(request):
    """
    Modern single-page payroll dashboard with Excel-like interface.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('home')
    
    # Check if user is Admin
    user_roles = [role.name for role in user.roles.all()]
    if 'Admin' not in user_roles:
        messages.error(request, "Only Admin can access payroll")
        return redirect('dashboard')
    
    # Get all payrolls for this tenant
    payrolls = Payroll.objects.filter(tenant=tenant).order_by('-created_at')
    
    # Get selected payroll
    selected_payroll = None
    payroll_items = []
    custom_columns = []
    approvals = []
    
    payroll_id = request.GET.get('payroll_id')
    if payroll_id:
        try:
            selected_payroll = Payroll.objects.get(id=payroll_id, tenant=tenant)
            payroll_items = selected_payroll.items.all().order_by('order', 'staff_name')
            custom_columns = selected_payroll.custom_columns.all().order_by('order')
            approvals = selected_payroll.approvals.all().order_by('level')
        except Payroll.DoesNotExist:
            messages.error(request, "Payroll not found")
    
    # Get all staff members in the tenant for approver selection
    from django.contrib.auth import get_user_model
    import json
    User = get_user_model()
    
    staff_users = User.objects.filter(tenant=tenant, is_active=True).exclude(id=user.id)
    staff_members = []
    for staff in staff_users:
        staff_members.append({
            'email': staff.email,
            'name': f"{staff.first_name} {staff.last_name}".strip() or staff.username,
            'role': staff.department.name if staff.department else 'Staff'
        })
    
    # Check if current user can approve
    can_user_approve = False
    if selected_payroll:
        can_user_approve = selected_payroll.can_user_approve(user)
    
    context = {
        'payrolls': payrolls,
        'selected_payroll': selected_payroll,
        'payroll_items': payroll_items,
        'custom_columns': custom_columns,
        'approvals': approvals,
        'staff_members': json.dumps(staff_members),
        'all_staff': staff_users,
        'can_user_approve': can_user_approve,
    }
    
    return render(request, 'payroll/payroll_dashboard.html', context)


@login_required
def payroll_list(request):
    """
    List all payrolls with filtering and pagination.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    if not user_can_approve_payroll(user):
        messages.error(request, "You don't have permission to access payroll")
        return redirect('dashboard')
    
    # Get all payrolls for tenant
    payrolls = Payroll.objects.filter(tenant=tenant).order_by('-period_start')
    
    # Filters
    status_filter = request.GET.get('status', '')
    year_filter = request.GET.get('year', '')
    search = request.GET.get('search', '')
    
    if status_filter:
        payrolls = payrolls.filter(status=status_filter)
    
    if year_filter:
        payrolls = payrolls.filter(period_start__year=year_filter)
    
    if search:
        payrolls = payrolls.filter(
            Q(notes__icontains=search) |
            Q(created_by__username__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(payrolls, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get available years for filter
    years = Payroll.objects.filter(tenant=tenant).dates('period_start', 'year', order='DESC')
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'year_filter': year_filter,
        'search': search,
        'years': years,
        'status_choices': Payroll.STATUS_CHOICES,
    }
    
    return render(request, 'payroll/list.html', context)


@login_required
def payroll_detail(request, pk):
    """
    View payroll details including all items and approval trail.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    payroll = get_object_or_404(Payroll, pk=pk, tenant=tenant)
    
    # Get payroll items
    items = payroll.items.select_related('staff', 'payment').order_by('staff_name')
    
    # Get summary
    summary = get_payroll_summary(payroll)
    
    # Get custom fields
    custom_fields = PayrollCustomField.objects.filter(
        tenant=tenant,
        is_active=True
    ).order_by('order')
    
    context = {
        'payroll': payroll,
        'items': items,
        'summary': summary,
        'custom_fields': custom_fields,
        'can_approve': user_can_approve_payroll(user),
        'can_pay': user_can_pay_payroll(user),
        'user_role': get_user_role_name(user),
    }
    
    return render(request, 'payroll/detail.html', context)


@login_required
def create_payroll(request):
    """
    Create new payroll with staff auto-fetch and custom fields.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    # Check if user is Admin
    user_roles = [role.name for role in user.roles.all()]
    if 'Admin' not in user_roles:
        messages.error(request, "Only Admin can create payroll")
        return redirect('payroll_dashboard')
    
    # Check if copying from previous month
    copy_from_id = request.GET.get('copy_from')
    copy_from_payroll = None
    
    if copy_from_id:
        copy_from_payroll = get_object_or_404(Payroll, pk=copy_from_id, tenant=tenant)
    
    if request.method == 'POST':
        form = PayrollForm(request.POST, tenant=tenant)
        
        if form.is_valid():
            with transaction.atomic():
                payroll = form.save(commit=False)
                payroll.tenant = tenant
                payroll.created_by = user
                payroll.save()
                
                # Auto-create payroll items for all active staff
                staff_list = get_staff_with_profiles(tenant)
                
                for staff in staff_list:
                    details = auto_fill_staff_details(staff)
                    
                    # If copying, get previous amounts
                    gross_amount = Decimal('0')
                    custom_field_values = {}
                    
                    if copy_from_payroll:
                        try:
                            prev_item = copy_from_payroll.items.get(staff=staff)
                            gross_amount = prev_item.gross_amount
                            custom_field_values = prev_item.custom_field_values
                        except PayrollItem.DoesNotExist:
                            pass
                    
                    PayrollItem.objects.create(
                        payroll=payroll,
                        staff=staff,
                        staff_name=details['staff_name'],
                        bank_name=details['bank_name'],
                        account_number=details['account_number'],
                        gross_amount=gross_amount,
                        custom_field_values=custom_field_values
                    )
                
                messages.success(request, f"Payroll created successfully with {staff_list.count()} staff members")
                return redirect('payroll_edit', pk=payroll.pk)
    else:
        initial_data = {}
        if copy_from_payroll:
            # Set next month dates
            initial_data['period_start'] = copy_from_payroll.period_start + relativedelta(months=1)
            initial_data['period_end'] = copy_from_payroll.period_end + relativedelta(months=1)
            initial_data['notification_days_before'] = copy_from_payroll.notification_days_before
        
        form = PayrollForm(initial=initial_data, tenant=tenant)
    
    context = {
        'form': form,
        'copy_from_payroll': copy_from_payroll,
    }
    
    return render(request, 'payroll/create.html', context)


@login_required
def payroll_edit(request, pk):
    """
    Edit payroll items with dynamic custom fields.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    payroll = get_object_or_404(Payroll, pk=pk, tenant=tenant)
    
    # Only allow editing if status is draft
    if payroll.status != 'draft':
        messages.error(request, f"Cannot edit payroll with status: {payroll.status}")
        return redirect('payroll_detail', pk=pk)
    
    # Check if user is Admin or HR
    user_roles = [role.name for role in user.roles.all()]
    if 'Admin' not in user_roles and 'HR' not in user_roles:
        messages.error(request, "Only Admin or HR can edit payroll")
        return redirect('payroll_detail', pk=pk)
    
    # Get custom fields
    custom_fields = PayrollCustomField.objects.filter(
        tenant=tenant,
        is_active=True
    ).order_by('order')
    
    # Get payroll items
    items = payroll.items.select_related('staff').order_by('staff_name')
    
    if request.method == 'POST':
        # Process bulk update
        updated_count = 0
        
        for item in items:
            gross_key = f'gross_{item.id}'
            
            if gross_key in request.POST:
                try:
                    gross_amount = Decimal(request.POST.get(gross_key, 0))
                    item.gross_amount = gross_amount
                    
                    # Update custom field values
                    custom_values = {}
                    for field in custom_fields:
                        field_key = f'custom_{field.name}_{item.id}'
                        value = request.POST.get(field_key, 0)
                        custom_values[field.name] = float(value) if value else 0
                    
                    item.custom_field_values = custom_values
                    item.save()  # This will auto-calculate net_amount
                    updated_count += 1
                    
                except (ValueError, Decimal.InvalidOperation):
                    messages.error(request, f"Invalid amount for {item.staff_name}")
                    continue
        
        messages.success(request, f"Updated {updated_count} payroll items")
        return redirect('payroll_detail', pk=pk)
    
    # Calculate summary
    summary = get_payroll_summary(payroll)
    
    context = {
        'payroll': payroll,
        'items': items,
        'custom_fields': custom_fields,
        'summary': summary,
    }
    
    return render(request, 'payroll/edit.html', context)


@login_required
def submit_for_approval(request, pk):
    """
    Submit payroll for approval workflow.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    payroll = get_object_or_404(Payroll, pk=pk, tenant=tenant)
    
    # Validate
    is_valid, error_msg = validate_payroll_for_approval(payroll)
    if not is_valid:
        messages.error(request, error_msg)
        return redirect('payroll_detail', pk=pk)
    
    # Submit
    payroll.submitted_by = user
    payroll.submitted_at = timezone.now()
    payroll.save()
    
    # Add to approval trail
    payroll.add_approval(user, get_user_role_name(user), 'submitted', 'Submitted for approval')
    
    messages.success(request, "Payroll submitted for approval")
    return redirect('payroll_detail', pk=pk)


@login_required
def approve_payroll(request, pk):
    """
    Approve or reject payroll.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    payroll = get_object_or_404(Payroll, pk=pk, tenant=tenant)
    
    # Check if user can approve (includes admin override)
    if not payroll.can_user_approve(user):
        messages.error(request, "You don't have permission to approve this payroll")
        return redirect('payroll_detail', pk=pk)
    
    # Check if already approved by this user
    for approval in payroll.approval_trail:
        if approval.get('user_id') == user.id and approval.get('action') == 'approved':
            messages.warning(request, "You have already approved this payroll")
            return redirect('payroll_detail', pk=pk)
    
    if request.method == 'POST':
        form = PayrollApprovalForm(request.POST)
        
        if form.is_valid():
            action = form.cleaned_data['action']
            comments = form.cleaned_data.get('comments', '')
            
            # Add to approval trail
            payroll.add_approval(user, get_user_role_name(user), action, comments)
            
            if action == 'approved':
                # Update approval level
                payroll.current_approval_level = get_user_highest_role_level(user)
                
                # Check if this is the highest role in the tenant
                # For simplicity, mark as fully approved
                payroll.is_fully_approved = True
                payroll.approved_by = user
                payroll.approved_at = timezone.now()
                payroll.status = 'approved'
                payroll.save()
                
                messages.success(request, "Payroll approved successfully")
            
            elif action == 'rejected':
                payroll.status = 'cancelled'
                payroll.save()
                messages.info(request, "Payroll rejected")
            
            elif action == 'returned':
                payroll.status = 'draft'
                payroll.submitted_at = None
                payroll.save()
                messages.info(request, "Payroll returned for revision")
            
            return redirect('payroll_detail', pk=pk)
    else:
        form = PayrollApprovalForm()
    
    context = {
        'payroll': payroll,
        'form': form,
    }
    
    return render(request, 'payroll/approve.html', context)


@login_required
def pay_payroll(request, pk):
    """
    Execute payment for approved payroll.
    Requires password verification.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    payroll = get_object_or_404(Payroll, pk=pk, tenant=tenant)
    
    # Validate
    is_valid, error_msg = validate_payroll_for_payment(payroll, user)
    if not is_valid:
        messages.error(request, error_msg)
        return redirect('payroll_detail', pk=pk)
    
    if request.method == 'POST':
        form = PayrollPasswordForm(request.POST, tenant=tenant)
        
        if form.is_valid():
            with transaction.atomic():
                # Create Payment records for each PayrollItem
                payment_count = 0
                
                for item in payroll.items.all():
                    # Get or create Payee for staff
                    payee, created = Payee.objects.get_or_create(
                        tenant=tenant,
                        user=item.staff,
                        defaults={
                            'name': item.staff_name,
                            'email': item.staff.email,
                            'account_name': item.staff_name,
                            'account_number': item.account_number,
                            'bank_name': item.bank_name,
                        }
                    )
                    
                    # Create Payment
                    payment = Payment.objects.create(
                        tenant=tenant,
                        payee=payee,
                        payment_type='salary',
                        direction='outgoing',
                        amount=item.gross_amount,
                        net_amount=item.net_amount,
                        payroll=payroll,
                        description=f"Salary for {payroll.period_start} to {payroll.period_end}",
                        status='pending',
                        payment_date=timezone.now(),
                        created_by=user
                    )
                    
                    # Link payment to payroll item
                    item.payment = payment
                    item.save()
                    
                    payment_count += 1
                
                # Update payroll status
                payroll.status = 'paid'
                payroll.save()
                
                # Update total amount
                payroll.update_total()
                
                messages.success(request, f"Payroll paid successfully! {payment_count} payments created.")
                return redirect('payroll_detail', pk=pk)
    else:
        form = PayrollPasswordForm(tenant=tenant)
    
    # Get summary
    summary = get_payroll_summary(payroll)
    
    context = {
        'payroll': payroll,
        'form': form,
        'summary': summary,
    }
    
    return render(request, 'payroll/pay.html', context)


@login_required
def manage_custom_fields(request):
    """
    Manage custom payroll fields (Tax, Pension, Bonus, etc.)
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    # Check if user is Admin or HR
    user_roles = [role.name for role in user.roles.all()]
    if 'Admin' not in user_roles and 'HR' not in user_roles:
        messages.error(request, "Only Admin or HR can manage custom fields")
        return redirect('payroll_dashboard')
    
    if request.method == 'POST':
        form = PayrollCustomFieldForm(request.POST)
        
        if form.is_valid():
            field = form.save(commit=False)
            field.tenant = tenant
            field.created_by = user
            field.save()
            
            messages.success(request, f"Custom field '{field.label}' created successfully")
            return redirect('manage_custom_fields')
    else:
        form = PayrollCustomFieldForm()
    
    # Get existing fields
    fields = PayrollCustomField.objects.filter(tenant=tenant).order_by('order', 'name')
    
    context = {
        'form': form,
        'fields': fields,
    }
    
    return render(request, 'payroll/custom_fields.html', context)


@login_required
def edit_custom_field(request, pk):
    """
    Edit an existing custom field.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('home')
    
    field = get_object_or_404(PayrollCustomField, pk=pk, tenant=tenant)
    
    # Check if user is Admin or HR
    user_roles = [role.name for role in user.roles.all()]
    if 'Admin' not in user_roles and 'HR' not in user_roles:
        messages.error(request, "Only Admin or HR can edit custom fields")
        return redirect('manage_custom_fields')
    
    if request.method == 'POST':
        form = PayrollCustomFieldForm(request.POST, instance=field)
        
        if form.is_valid():
            form.save()
            messages.success(request, f"Custom field '{field.label}' updated successfully")
            return redirect('manage_custom_fields')
    else:
        form = PayrollCustomFieldForm(instance=field)
    
    context = {
        'form': form,
        'field': field,
        'is_edit': True,
    }
    
    return render(request, 'payroll/edit_custom_field.html', context)


@login_required
def delete_custom_field(request, pk):
    """
    Delete a custom field.
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('home')
    
    field = get_object_or_404(PayrollCustomField, pk=pk, tenant=tenant)
    
    # Check if user is Admin or HR
    user_roles = [role.name for role in user.roles.all()]
    if 'Admin' not in user_roles and 'HR' not in user_roles:
        messages.error(request, "Only Admin or HR can delete custom fields")
        return redirect('manage_custom_fields')
    
    if request.method == 'POST':
        field_name = field.label
        field.delete()
        messages.success(request, f"Custom field '{field_name}' deleted")
        return redirect('manage_custom_fields')
    
    return render(request, 'payroll/delete_custom_field.html', {'field': field})


@login_required
def set_payroll_password_view(request):
    """
    Set or change payroll password (Admin only).
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    if not tenant:
        messages.error(request, "Payroll is only available for organization accounts")
        return redirect('dashboard')
    
    # Check if user is Admin
    user_roles = [role.name for role in user.roles.all()]
    if 'Admin' not in user_roles:
        messages.error(request, "Only Admin can set payroll password")
        return redirect('payroll_dashboard')
    
    if request.method == 'POST':
        form = SetPayrollPasswordForm(request.POST)
        
        if form.is_valid():
            password = form.cleaned_data['new_password']
            set_payroll_password(tenant, password)
            
            messages.success(request, "Payroll password set successfully")
            return redirect('payroll_dashboard')
    else:
        form = SetPayrollPasswordForm()
    
    context = {
        'form': form,
        'password_exists': has_payroll_password(tenant),
    }
    
    return render(request, 'payroll/set_password.html', context)


# AJAX Endpoints for Modern Payroll Dashboard

@login_required
def payroll_create(request):
    """Create a new payroll via AJAX"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    tenant = request.effective_tenant
    user = request.effective_user
    
    try:
        import json
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        data = json.loads(request.body)
        title = data.get('title')
        pin = data.get('pin')
        approvers = data.get('approvers', [])
        
        if not title or not pin:
            return JsonResponse({'success': False, 'error': 'Title and PIN are required'})
        
        # Create payroll
        with transaction.atomic():
            payroll = Payroll.objects.create(
                tenant=tenant,
                title=title,
                created_by=user
            )
            payroll.set_pin(pin)
            payroll.save()
            
            # Create approval workflow
            for level, approver_email in enumerate(approvers, start=1):
                try:
                    approver_user = User.objects.get(email=approver_email, tenant=tenant)
                    PayrollApproval.objects.create(
                        payroll=payroll,
                        approver=approver_user,
                        level=level,
                        status='pending'
                    )
                except User.DoesNotExist:
                    pass  # Skip invalid emails
        
        return JsonResponse({'success': True, 'payroll_id': payroll.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_clone(request):
    """Clone a payroll structure without data"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    tenant = request.effective_tenant
    user = request.effective_user
    
    try:
        import json
        import logging
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        logger = logging.getLogger(__name__)
        logger.info(f"Clone request from user {user.id} for tenant {tenant.id}")
        
        data = json.loads(request.body)
        source_payroll_id = data.get('source_payroll_id')
        title = data.get('title')
        pin = data.get('pin')
        
        logger.info(f"Clone params: source={source_payroll_id}, title={title}")
        
        if not source_payroll_id or not title or not pin:
            return JsonResponse({'success': False, 'error': 'Source payroll, title and PIN are required'})
        
        # Get source payroll
        try:
            source_payroll = Payroll.objects.get(id=source_payroll_id, tenant=tenant)
            logger.info(f"Found source payroll: {source_payroll.title}")
        except Payroll.DoesNotExist:
            logger.error(f"Source payroll {source_payroll_id} not found")
            return JsonResponse({'success': False, 'error': 'Source payroll not found'})
        
        # Clone payroll structure
        with transaction.atomic():
            # Create new payroll
            new_payroll = Payroll.objects.create(
                tenant=tenant,
                title=title,
                created_by=user
            )
            new_payroll.set_pin(pin)
            new_payroll.save()
            logger.info(f"Created new payroll: {new_payroll.id}")
            
            # Clone custom columns
            columns_count = 0
            for column in source_payroll.custom_columns.all().order_by('order'):
                PayrollCustomColumn.objects.create(
                    payroll=new_payroll,
                    name=column.name,
                    operation=column.operation,
                    order=column.order
                )
                columns_count += 1
            logger.info(f"Cloned {columns_count} columns")
            
            # Clone approval workflow
            approvals_count = 0
            for approval in source_payroll.approvals.all():
                PayrollApproval.objects.create(
                    payroll=new_payroll,
                    approver=approval.approver,
                    level=approval.level,
                    status='pending'
                )
                approvals_count += 1
            logger.info(f"Cloned {approvals_count} approvals")
        
        logger.info(f"Clone successful: new payroll ID {new_payroll.id}")
        return JsonResponse({'success': True, 'payroll_id': new_payroll.id})
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Clone error: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'})


@login_required
def payroll_add_row(request):
    """Add a new row to payroll"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    tenant = request.effective_tenant
    
    try:
        import json
        data = json.loads(request.body)
        payroll_id = data.get('payroll_id')
        
        payroll = Payroll.objects.get(id=payroll_id, tenant=tenant)
        
        # Check if payroll is locked or paid
        if payroll.status == 'paid' or payroll.is_locked:
            return JsonResponse({'success': False, 'error': 'Cannot modify a paid or locked payroll'})
        
        # Get next order
        last_item = payroll.items.order_by('-order').first()
        next_order = (last_item.order + 1) if last_item else 0
        
        # Create new item
        PayrollItem.objects.create(
            payroll=payroll,
            staff_name='New Staff',
            gross_amount=Decimal('0.00'),
            order=next_order
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_add_column(request):
    """Add a new column to payroll"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    tenant = request.effective_tenant
    
    try:
        import json
        data = json.loads(request.body)
        payroll_id = data.get('payroll_id')
        name = data.get('name')
        operation = data.get('operation', 'subtract')
        
        payroll = Payroll.objects.get(id=payroll_id, tenant=tenant)
        
        # Check if payroll is locked or paid
        if payroll.status == 'paid' or payroll.is_locked:
            return JsonResponse({'success': False, 'error': 'Cannot modify a paid or locked payroll'})
        
        # Create column
        PayrollCustomColumn.objects.create(
            payroll=payroll,
            name=name,
            operation=operation
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_update_item(request):
    """Update a payroll item field"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        import json
        data = json.loads(request.body)
        item_id = data.get('item_id')
        field = data.get('field')
        value = data.get('value')
        
        item = PayrollItem.objects.get(id=item_id)
        
        # Check if payroll is locked or paid
        if item.payroll.status == 'paid' or item.payroll.is_locked:
            return JsonResponse({'success': False, 'error': 'Cannot modify a paid or locked payroll'})
        
        if field == 'staff_name':
            item.staff_name = value
        elif field == 'gross_amount':
            item.gross_amount = Decimal(value)
        
        item.save()
        
        return JsonResponse({
            'success': True,
            'net_amount': str(item.net_amount)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_update_column_value(request):
    """Update a column value for a payroll item"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        import json
        data = json.loads(request.body)
        item_id = data.get('item_id')
        column_name = data.get('column_name')
        value = data.get('value')
        
        item = PayrollItem.objects.get(id=item_id)
        
        # Check if payroll is locked or paid
        if item.payroll.status == 'paid' or item.payroll.is_locked:
            return JsonResponse({'success': False, 'error': 'Cannot modify a paid or locked payroll'})
        
        # Update column values
        if not item.column_values:
            item.column_values = {}
        
        item.column_values[column_name] = float(value)
        item.save()
        
        return JsonResponse({
            'success': True,
            'net_amount': str(item.net_amount)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_delete_row(request):
    """Delete a payroll item"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        import json
        data = json.loads(request.body)
        item_id = data.get('item_id')
        
        item = PayrollItem.objects.get(id=item_id)
        payroll = item.payroll
        
        # Check if payroll is locked or paid
        if payroll.status == 'paid' or payroll.is_locked:
            return JsonResponse({'success': False, 'error': 'Cannot modify a paid or locked payroll'})
        
        item.delete()
        
        # Update payroll totals
        payroll.update_totals()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_submit_approval(request):
    """Submit payroll for approval or approve/reject payroll"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    tenant = request.effective_tenant
    user = request.effective_user
    
    try:
        import json
        from django.utils import timezone
        data = json.loads(request.body)
        payroll_id = data.get('payroll_id')
        action = data.get('action')  # 'approve' or 'reject' or None (for submit)
        comments = data.get('comments', '')
        
        payroll = Payroll.objects.get(id=payroll_id, tenant=tenant)
        
        # If action is approve or reject
        if action in ['approve', 'reject']:
            # Check if user can approve
            if not payroll.can_user_approve(user):
                return JsonResponse({'success': False, 'error': 'You do not have permission to approve this payroll'})
            
            if action == 'approve':
                # Find user's approval or create admin approval
                approval = payroll.approvals.filter(approver=user, status='pending').first()
                
                if not approval:
                    # Admin override - approve all pending approvals
                    if user == tenant.admin or user == tenant.created_by:
                        for pending_approval in payroll.approvals.filter(status='pending'):
                            pending_approval.approve(comments)
                        return JsonResponse({'success': True})
                    else:
                        return JsonResponse({'success': False, 'error': 'No pending approval found for you'})
                else:
                    approval.approve(comments)
                    return JsonResponse({'success': True})
            
            elif action == 'reject':
                approval = payroll.approvals.filter(approver=user, status='pending').first()
                if not approval:
                    # Admin can reject
                    if user == tenant.admin or user == tenant.created_by:
                        # Reject all and reset payroll
                        for pending_approval in payroll.approvals.all():
                            pending_approval.status = 'pending'
                            pending_approval.save()
                        payroll.status = 'draft'
                        payroll.save()
                        return JsonResponse({'success': True})
                    else:
                        return JsonResponse({'success': False, 'error': 'No pending approval found for you'})
                else:
                    approval.reject(comments)
                    return JsonResponse({'success': True})
        else:
            # Submit for approval
            if payroll.submit_for_approval():
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'No approvers configured'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_process_payment(request):
    """Process payroll payment with PIN verification"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    tenant = request.effective_tenant
    user = request.effective_user
    
    try:
        import json
        import logging
        from django.utils import timezone
        
        logger = logging.getLogger(__name__)
        
        data = json.loads(request.body)
        payroll_id = data.get('payroll_id')
        pin = data.get('pin')
        
        logger.info(f"Payment request: payroll_id={payroll_id}, user={user.email}")
        
        if not payroll_id:
            return JsonResponse({'success': False, 'error': 'Payroll ID is required'})
        
        if not pin:
            return JsonResponse({'success': False, 'error': 'PIN is required'})
        
        try:
            payroll = Payroll.objects.get(id=payroll_id, tenant=tenant)
        except Payroll.DoesNotExist:
            logger.error(f"Payroll {payroll_id} not found")
            return JsonResponse({'success': False, 'error': 'Payroll not found'})
        
        logger.info(f"Payroll found: {payroll.title}, status={payroll.status}")
        
        # Verify PIN
        if not payroll.check_pin(pin):
            logger.warning(f"Incorrect PIN for payroll {payroll_id}")
            return JsonResponse({'success': False, 'error': 'Incorrect PIN. Please check and try again.'})
        
        logger.info("PIN verified successfully")
        
        # Check if approved
        if payroll.status != 'approved':
            logger.warning(f"Payroll {payroll_id} not approved, status={payroll.status}")
            return JsonResponse({'success': False, 'error': f'Payroll must be approved first. Current status: {payroll.status}'})
        
        # Process payment
        with transaction.atomic():
            payroll.status = 'paid'
            payroll.is_locked = True
            payroll.paid_at = timezone.now()
            payroll.paid_by = user
            payroll.save()
        
        logger.info(f"Payment processed successfully for payroll {payroll_id}")
        return JsonResponse({'success': True})
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Invalid request data'})
    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'})


@login_required
def payroll_update_column(request):
    """Update a payroll column"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        import json
        data = json.loads(request.body)
        column_id = data.get('column_id')
        name = data.get('name')
        operation = data.get('operation')
        
        column = PayrollCustomColumn.objects.get(id=column_id)
        
        # Check if payroll is locked or paid
        if column.payroll.status == 'paid' or column.payroll.is_locked:
            return JsonResponse({'success': False, 'error': 'Cannot modify a paid or locked payroll'})
        column.name = name
        column.operation = operation
        column.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_delete_column(request):
    """Delete a payroll column"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        import json
        data = json.loads(request.body)
        column_id = data.get('column_id')
        
        column = PayrollCustomColumn.objects.get(id=column_id)
        
        # Check if payroll is locked or paid
        if column.payroll.status == 'paid' or column.payroll.is_locked:
            return JsonResponse({'success': False, 'error': 'Cannot modify a paid or locked payroll'})
        
        column.delete()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def payroll_export(request):
    """Export payroll to Excel"""
    import csv
    from django.http import HttpResponse
    
    tenant = request.effective_tenant
    payroll_id = request.GET.get('payroll_id')
    
    try:
        payroll = Payroll.objects.get(id=payroll_id, tenant=tenant)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="payroll_{payroll.title}.csv"'
        
        writer = csv.writer(response)
        
        # Header
        headers = ['Staff Name', 'Gross Amount']
        for column in payroll.custom_columns.all().order_by('order'):
            headers.append(f"{column.name} ({column.get_operation_display()})")
        headers.append('Net Amount')
        
        writer.writerow(headers)
        
        # Data
        for item in payroll.items.all().order_by('order', 'staff_name'):
            row = [item.staff_name, item.gross_amount]
            for column in payroll.custom_columns.all().order_by('order'):
                row.append(item.column_values.get(column.name, 0))
            row.append(item.net_amount)
            writer.writerow(row)
        
        return response
    except Exception as e:
        messages.error(request, f"Export failed: {str(e)}")
        return redirect('payroll_dashboard')
