from django.utils import timezone
from django.contrib import messages
import logging
from django.contrib.auth.decorators import login_required, user_passes_test
from documents.forms import CompanyDocumentForm, CompanyProfileForm, BankVerificationForm, BankConfirmationForm, Tenant, UserBankVerificationForm, UserProfileForm
from documents.models import CompanyProfile, CompanyDocument, Remittance, StaffProfile, StaffDocument, CustomUser, UserProfile
from django.http import HttpResponseForbidden, JsonResponse

from documents.viewfuncs.send_mails import send_bank_verification_confirmation_email, send_bank_verification_rejection_email, send_bank_verification_request_email, send_bank_verification_confirmation_for_user_email, send_bank_verification_rejection_for_user_email, send_bank_verification_request_for_staff_email
from ..rba_decorators import is_admin 
from django.shortcuts import redirect, render, get_object_or_404
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from ..helper_funcs.staff_tenant_or_user import get_tenant_or_staff


logger = logging.getLogger(__name__)


@login_required
@user_passes_test(is_admin)
def edit_company_profile(request):
    """
    Edit company profile.

    :param request: The request object
    :return: A JSON response containing the company profile data
    :rtype: JsonResponse
    """
    # if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
    #     logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
    #     return HttpResponseForbidden("You are not authorized for this company.")
    # if not is_admin(request.effective_user) or not request.user.is_staff:
    #     return HttpResponseForbidden("You are not authorized for this company.")

    tenant = get_tenant_or_staff(request)
    
    company_profile, created = CompanyProfile.objects.get_or_create(
        tenant=request.effective_tenant,
        defaults={'company_name': request.effective_tenant.name}
    )
    
    if request.method == "POST":
        form = CompanyProfileForm(request.POST, request.FILES, instance=company_profile)
        if form.is_valid():
            form.save()
            return redirect("view_company_profile")
    else:
        form = CompanyProfileForm(instance=company_profile)
        document_form = CompanyDocumentForm()
    return render(request, "admin/edit_company_profile.html", {"form": form, 'profile': company_profile, 'document_form': document_form})

@login_required
def bank_verification(request):
    """
    Separate view for bank verification
    """
    # tenant = request.user.tenant
    tenant = request.effective_tenant
    user = request.effective_user

    if user.is_personal:
        try:
            user_profile = user.user_profile
        except UserProfile.DoesNotExist:
            messages.error(request, "Please complete your profile first.")
            return redirect('edit_user_profile')
    elif not is_admin(user):
        try:
            staff_profile = user.staff_profile
        except StaffProfile.DoesNotExist:
            messages.error(request, "Please complete your staff profile first.")
            return redirect('edit_my_profile')
    else:
        try:
            company_profile = tenant.company_profile
        except CompanyProfile.DoesNotExist:
            messages.error(request, "Please complete your company profile first.")
            return redirect('edit_company_profile')

    if user.is_personal:    
        if request.method == "POST":
            form = UserBankVerificationForm(request.POST, instance=user_profile)
            if form.is_valid():
                # Save bank details but don't mark as verified yet
                form.save()
                
                # Reset verification status since details changed
                user_profile.bank_verified = False
                user_profile.bank_verification_date = None
                user_profile.save()
                
                messages.success(request, "Bank details updated successfully!")
                messages.info(request, "Your bank details will be verified before processing remittances.")
                
                # Redirect to confirmation page
                return redirect('bank_confirmation')
        else:
            form = UserBankVerificationForm(instance=user_profile)
        
        context = {
            'form': form,
            'company_profile': user_profile,
            'has_bank_details': user_profile.has_complete_bank_details(),
            'bank_verified': user_profile.bank_verified,
        }
    elif not is_admin(user):
        if request.method == "POST":
            form = BankVerificationForm(request.POST, instance=staff_profile)
            if form.is_valid():
                # Save bank details but don't mark as verified yet
                form.save()
                
                # Reset verification status since details changed
                staff_profile.bank_verified = False
                staff_profile.bank_verification_date = None
                staff_profile.save()
                
                messages.success(request, "Bank details updated successfully!")
                messages.info(request, "Your bank details will be verified before processing remittances.")
                
                # Redirect to confirmation page
                return redirect('bank_confirmation')
        else:
            form = BankVerificationForm(instance=staff_profile)
        
        context = {
            'form': form,
            'company_profile': staff_profile,
            'has_bank_details': staff_profile.has_complete_bank_details(),
            'bank_verified': staff_profile.bank_verified,
        }
    else:
        if request.method == "POST":
            form = BankVerificationForm(request.POST, instance=company_profile)
            if form.is_valid():
                # Save bank details but don't mark as verified yet
                form.save()
                
                # Reset verification status since details changed
                company_profile.bank_verified = False
                company_profile.bank_verification_date = None
                company_profile.save()
                
                messages.success(request, "Bank details updated successfully!")
                messages.info(request, "Your bank details will be verified before processing remittances.")
                
                # Redirect to confirmation page
                return redirect('bank_confirmation')
        else:
            form = BankVerificationForm(instance=company_profile)
        
        context = {
            'form': form,
            'company_profile': company_profile,
            'has_bank_details': company_profile.has_complete_bank_details(),
            'bank_verified': company_profile.bank_verified,
        }
        
        
    return render(request, 'wallet/bank_verification.html', context)
    

# NO 1
@login_required
def bank_confirmation(request):
    """
    Page for tenant to confirm their bank details
    """
    # tenant = request.user.tenant
    tenant = request.effective_tenant
    user = request.effective_user
    
    if user.is_personal:
        try:
            user_profile = user.user_profile
        except UserProfile.DoesNotExist:
            messages.error(request, "Please complete your profile first.")
            return redirect('edit_user_profile')
    elif not is_admin(user):
        try:
            staff_profile = user.staff_profile
        except StaffProfile.DoesNotExist:
            messages.error(request, "Please complete your staff profile first.")
            return redirect('edit_my_profile')
    else:
        try:
            company_profile = tenant.company_profile
        except CompanyProfile.DoesNotExist:
            messages.error(request, "Please complete your company profile first.")
            return redirect('edit_company_profile')
        
    if user.is_personal:
        if not user_profile.has_complete_bank_details():
            messages.warning(request, "Please add your bank details first.")
            return redirect('bank_verification')
    elif not is_admin(user):
        if not staff_profile.has_complete_bank_details():
            messages.warning(request, "Please add your bank details first.")
            return redirect('bank_verification')
    else:
        if not company_profile.has_complete_bank_details():
            messages.warning(request, "Please add your bank details first.")
            return redirect('bank_verification')

    if user.is_personal:
        if request.method == "POST":
            form = UserBankVerificationForm(request.POST)
            if form.is_valid():
                # Mark as verified by tenant
                user_profile.bank_verified = True
                user_profile.bank_verification_date = timezone.now()
                user_profile.save()
                
                messages.success(request, "Bank details confirmed! Admin will verify before processing remittances.")
                
                # Send email to owner for verification
                send_bank_verification_request_email(request, user_profile)
                
                return redirect('view_company_profile')
        else:
            form = UserBankVerificationForm()
        
        context = {
            'form': form,
            'company_profile': user_profile,
            'bank_details': user_profile.get_formatted_bank_details(),
        }
    elif not is_admin(user):
        if request.method == "POST":
            form = BankConfirmationForm(request.POST)
            if form.is_valid():
                # Mark as verified by tenant
                staff_profile.bank_verified = True
                staff_profile.bank_verification_date = timezone.now()
                staff_profile.save()
                
                messages.success(request, "Bank details confirmed! Admin will verify before processing remittances.")
                
                # Send email to admin for verification
                send_bank_verification_request_for_staff_email(request, staff_profile)
                
                return redirect('view_my_profile')
        else:
            form = BankConfirmationForm()
        
        context = {
            'form': form,
            'company_profile': staff_profile,
            'bank_details': staff_profile.get_formatted_bank_details(),
        }
    else:
        if request.method == "POST":
            form = BankConfirmationForm(request.POST)
            if form.is_valid():
                # Mark as verified by tenant
                company_profile.bank_verified = True
                company_profile.bank_verification_date = timezone.now()
                company_profile.save()
                
                messages.success(request, "Bank details confirmed! Admin will verify before processing remittances.")
                
                # Send email to admin for verification
                send_bank_verification_request_email(request, company_profile)
                
                return redirect('view_company_profile')
        else:
            form = BankConfirmationForm()
        
        context = {
            'form': form,
            'company_profile': company_profile,
            'bank_details': company_profile.get_formatted_bank_details(),
        }
    
    return render(request, 'wallet/bank_confirmation.html', context)
# NO 2


@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_verify_bank_details(request, tenant_id):
    """
    Admin view to verify tenant bank details
    """
    tenant = get_object_or_404(Tenant, id=tenant_id)
    
    # Get the company profile for the specific tenant
    try:
        company_profile = CompanyProfile.objects.get(tenant=tenant)
    except CompanyProfile.DoesNotExist:
        messages.error(request, f"{tenant.name} does not have a company profile.")
        return redirect('admin_remittance_dashboard')
    
    if not company_profile.has_complete_bank_details():
        messages.error(request, f"{tenant.name} has incomplete bank details.")
        return redirect('admin_remittance_dashboard')
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'verify':
            # Update company profile
            company_profile.bank_verified = True
            company_profile.bank_verification_date = timezone.now()
            company_profile.verified_by = request.user
            company_profile.save()
            
            # Update all pending remittances for this tenant
            pending_remittances = Remittance.objects.filter(
                tenant=tenant,
                bank_confirmation__in=['pending', 'rejected']
            )
            
            for remittance in pending_remittances:
                remittance.bank_confirmation = 'confirmed'
                remittance.confirmed_by = request.user
                remittance.save()
            
            messages.success(request, f"Bank details for {tenant.name} have been confirmed and {pending_remittances.count()} remittance(s) updated.")
            
            # Send email to tenant
            try:
                send_bank_verification_confirmation_email(company_profile, request.user)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Email sending failed for bank verification: {str(e)}")
            
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '').strip()
            if not rejection_reason:
                messages.error(request, "Please provide a reason for rejection.")
                return redirect('admin_remittance_dashboard')
                
            # Update company profile
            company_profile.bank_verified = False
            company_profile.bank_verification_date = None
            company_profile.verified_by = None
            company_profile.bank_rejection_reason = rejection_reason
            company_profile.save()
            
            # Update all pending remittances for this tenant
            pending_remittances = Remittance.objects.filter(
                tenant=tenant,
                bank_confirmation__in=['pending', 'rejected']
            )
            
            for remittance in pending_remittances:
                remittance.bank_confirmation = 'rejected'
                remittance.confirmed_by = request.user
                remittance.save()
            
            messages.warning(request, f"Bank details for {tenant.name} have been rejected and {pending_remittances.count()} remittance(s) updated.")
            
            # Send email to tenant
            try:
                send_bank_verification_rejection_email(request, company_profile)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Email sending failed for bank rejection: {str(e)}")
        
        # Always redirect back to admin_remittance_dashboard
        return redirect('admin_remittance_dashboard')
    
    # If GET request, redirect to dashboard
    return redirect('admin_remittance_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_verify_user_bank_details(request, user_id):
    """
    Admin view to verify user bank details
    """
    user = get_object_or_404(CustomUser, id=user_id)
    
    # Get the company profile for the specific user
    try:
        user_profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        messages.error(request, f"{user.username} does not have a company profile.")
        return redirect('admin_remittance_dashboard')
    
    if not user_profile.has_complete_bank_details():
        messages.error(request, f"{user.username} has incomplete bank details.")
        return redirect('admin_remittance_dashboard')
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'verify':
            # Update company profile
            user_profile.bank_verified = True
            user_profile.bank_verification_date = timezone.now()
            user_profile.verified_by = request.user
            user_profile.save()
            
            # Update all pending remittances for this tenant
            pending_remittances = Remittance.objects.filter(
                owner=user,
                bank_confirmation__in=['pending', 'rejected']
            )
            
            for remittance in pending_remittances:
                remittance.bank_confirmation = 'confirmed'
                remittance.confirmed_by = request.user
                remittance.save()
            
            messages.success(request, f"Bank details for {user.username} have been confirmed and {pending_remittances.count()} remittance(s) updated.")
            
            # Send email to tenant
            try:
                send_bank_verification_confirmation_for_user_email(user_profile, request.user)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Email sending failed for bank verification: {str(e)}")
            
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '').strip()
            if not rejection_reason:
                messages.error(request, "Please provide a reason for rejection.")
                return redirect('admin_remittance_dashboard')
                
            # Update user profile
            user_profile.bank_verified = False
            user_profile.bank_verification_date = None
            # user_profile.verified_by = None
            user_profile.bank_rejection_reason = rejection_reason
            user_profile.save()
            
            # Update all pending remittances for this tenant
            pending_remittances = Remittance.objects.filter(
                owner=user,
                bank_confirmation__in=['pending', 'rejected']
            )
            
            for remittance in pending_remittances:
                remittance.bank_confirmation = 'rejected'
                remittance.confirmed_by = request.user
                remittance.save()
            
            messages.warning(request, f"Bank details for {user.username} have been rejected and {pending_remittances.count()} remittance(s) updated.")
            
            # Send email to tenant
            try:
                send_bank_verification_rejection_for_user_email(request, user_profile)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Email sending failed for bank rejection: {str(e)}")
        
        # Always redirect back to admin_remittance_dashboard
        return redirect('admin_remittance_dashboard')
    
    # If GET request, redirect to dashboard
    return redirect('admin_remittance_dashboard')


def send_bank_verification_email(request, company_profile):
    """Send bank verification email to tenant"""
    from django.template.loader import render_to_string
    from django.core.mail import send_mail
    from django.conf import settings
    
    subject = "Bank Details Verification Required"
    
    context = {
        'company_profile': company_profile,
        'tenant': company_profile.tenant,
        'admin_name': request.user.get_full_name() or request.user.username,
        'verification_url': f"{settings.SITE_URL}/verify-bank-details/{company_profile.id}/"
    }
    
    html_message = render_to_string('emails/bank_verification.html', context)
    plain_message = render_to_string('emails/bank_verification.txt', context)
    
    tenant_email = company_profile.email or company_profile.tenant.admin.email
    
    if tenant_email:
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[tenant_email],
                html_message=html_message,
                fail_silently=False,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send bank verification email: {e}")
            return False
    return False

@login_required
@user_passes_test(is_admin)
def verify_bank_details(request, profile_id):
    """Tenant verifies their bank details"""
    company_profile = get_object_or_404(CompanyProfile, id=profile_id, tenant=request.tenant)
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'confirm':
            company_profile.bank_verified = True
            company_profile.bank_verification_date = timezone.now()
            company_profile.save()
            
            messages.success(request, "Bank details verified successfully!")
            return redirect('view_company_profile')
        elif action == 'update':
            # Redirect to edit page
            return redirect('edit_company_profile')
    
    context = {
        'company_profile': company_profile,
    }
    
    return render(request, 'admin/verify_bank_details.html', context)


@login_required
@user_passes_test(is_admin)
def add_company_document(request):
    """
    Add a company document.

    :param request: The request object
    :return: A JSON response containing the added company document data
    :rtype: JsonResponse
    """
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    if request.method == 'POST':
        form = CompanyDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.tenant = request.user.tenant
            document.company_profile = get_object_or_404(CompanyProfile, tenant=request.tenant)
            document.save()
            return JsonResponse({
                'success': True,
                'document': {
                    'id': document.id,
                    'description': document.description or document.document_type,
                    'file_url': document.file.url,
                    'document_type': document.get_document_type_display(),
                    'uploaded_at': document.uploaded_at.strftime('%B %d, %Y')
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@login_required
@user_passes_test(is_admin)
def delete_company_document(request, document_id):
    """
    Delete a company document.

    :param request: The request object
    :param document_id: The ID of the company document to be deleted
    :return: A JSON response containing the success status of the deletion
    :rtype: JsonResponse
    """
    if hasattr(request, 'tenant') and request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    
    try:
        # Get the user's StaffProfile (assuming one profile per user)
        company_profile = CompanyProfile.objects.get(tenant=request.tenant)
        document = get_object_or_404(CompanyDocument, id=document_id, company_profile=company_profile)
        if request.method == 'POST':
            document.delete()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)
        # raise BadRequest('Invalid request method')
    except StaffProfile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Staff profile not found'}, status=404)
    except StaffDocument.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Document not found or not owned by user'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

