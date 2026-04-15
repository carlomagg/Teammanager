# documents/viewfuncs/kyc_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from documents.kyc_models import UserKYC, StaffKYC, CompanyKYB, CompanyDirector
from documents.kyc_forms import UserKYCForm, StaffKYCForm, CompanyKYBForm, CompanyDirectorForm
from documents.models import UserProfile, StaffProfile, CompanyProfile


@login_required
def kyc_status_view(request):
    """View KYC/KYB status for current user"""
    user = request.user
    context = {
        'user': user,
        'kyc': None,
        'kyb': None,
        'is_personal': user.is_personal,
    }
    
    # Check if user has personal profile
    if user.is_personal:
        try:
            user_profile = user.user_profile
            kyc, created = UserKYC.objects.get_or_create(user_profile=user_profile)
            context['kyc'] = kyc
            context['profile'] = user_profile
        except UserProfile.DoesNotExist:
            messages.warning(request, "Please complete your profile first before KYC.")
            return redirect('edit_user_profile')
    else:
        # Staff with tenant
        try:
            staff_profile = user.staff_profile
            kyc, created = StaffKYC.objects.get_or_create(staff_profile=staff_profile)
            context['kyc'] = kyc
            context['profile'] = staff_profile
        except StaffProfile.DoesNotExist:
            messages.warning(request, "Please complete your staff profile first before KYC.")
            return redirect('edit_my_profile')
        
        # Check if user is admin and can view KYB
        if user.is_superuser or user.roles.filter(name='Admin').exists():
            try:
                company_profile = user.tenant.company_profile
                kyb, created = CompanyKYB.objects.get_or_create(company_profile=company_profile)
                context['kyb'] = kyb
                context['company_profile'] = company_profile
                context['directors'] = company_profile.directors.all()
            except CompanyProfile.DoesNotExist:
                pass
    
    return render(request, 'kyc/kyc_status.html', context)


@login_required
def complete_user_kyc(request):
    """Complete KYC for personal user"""
    user = request.user
    
    if not user.is_personal:
        messages.error(request, "This page is for personal accounts only.")
        return redirect('kyc_status')
    
    try:
        user_profile = user.user_profile
    except UserProfile.DoesNotExist:
        messages.warning(request, "Please complete your profile first.")
        return redirect('edit_user_profile')
    
    kyc, created = UserKYC.objects.get_or_create(user_profile=user_profile)
    
    if request.method == 'POST':
        form = UserKYCForm(request.POST, request.FILES, instance=kyc, user_profile=user_profile)
        if form.is_valid():
            kyc = form.save(commit=False)
            kyc.kyc_status = 'submitted'
            kyc.save()
            
            # Send notification email to admin
            send_kyc_notification_email(user, 'User KYC')
            
            messages.success(request, "Your KYC information has been submitted successfully. We'll review it shortly.")
            return redirect('kyc_status')
    else:
        form = UserKYCForm(instance=kyc, user_profile=user_profile)
    
    context = {
        'form': form,
        'kyc': kyc,
        'profile': user_profile,
        'missing_profile_fields': form.get_missing_profile_fields(),
    }
    return render(request, 'kyc/complete_user_kyc.html', context)


@login_required
def complete_staff_kyc(request):
    """Complete KYC for staff user"""
    user = request.user
    
    if user.is_personal:
        messages.error(request, "This page is for staff accounts only.")
        return redirect('kyc_status')
    
    try:
        staff_profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        messages.warning(request, "Please complete your staff profile first.")
        return redirect('edit_my_profile')
    
    kyc, created = StaffKYC.objects.get_or_create(staff_profile=staff_profile)
    
    if request.method == 'POST':
        form = StaffKYCForm(request.POST, request.FILES, instance=kyc, staff_profile=staff_profile)
        if form.is_valid():
            kyc = form.save(commit=False)
            kyc.kyc_status = 'submitted'
            kyc.save()
            
            # Send notification email to admin
            send_kyc_notification_email(user, 'Staff KYC')
            
            messages.success(request, "Your KYC information has been submitted successfully. We'll review it shortly.")
            return redirect('kyc_status')
    else:
        form = StaffKYCForm(instance=kyc, staff_profile=staff_profile)
    
    context = {
        'form': form,
        'kyc': kyc,
        'profile': staff_profile,
        'missing_profile_fields': form.get_missing_profile_fields(),
    }
    return render(request, 'kyc/complete_staff_kyc.html', context)


@login_required
def complete_company_kyb(request):
    """Complete KYB for company"""
    user = request.user
    
    if user.is_personal:
        messages.error(request, "This page is for business accounts only.")
        return redirect('kyc_status')
    
    # Check if user has permission
    if not (user.is_superuser or user.roles.filter(name='Admin').exists()):
        messages.error(request, "You don't have permission to complete company KYB.")
        return redirect('kyc_status')
    
    try:
        company_profile = user.tenant.company_profile
    except CompanyProfile.DoesNotExist:
        messages.warning(request, "Please complete company profile first.")
        return redirect('edit_company_profile')
    
    kyb, created = CompanyKYB.objects.get_or_create(company_profile=company_profile)
    
    if request.method == 'POST':
        form = CompanyKYBForm(request.POST, request.FILES, instance=kyb, company_profile=company_profile)
        if form.is_valid():
            kyb = form.save(commit=False)
            kyb.kyb_status = 'submitted'
            kyb.save()
            
            # Send notification email
            send_kyb_notification_email(user, company_profile)
            
            messages.success(request, "Company KYB information has been submitted successfully. We'll review it shortly.")
            return redirect('kyc_status')
    else:
        form = CompanyKYBForm(instance=kyb, company_profile=company_profile)
    
    context = {
        'form': form,
        'kyb': kyb,
        'company_profile': company_profile,
        'directors': company_profile.directors.all(),
        'missing_profile_fields': form.get_missing_profile_fields(),
    }
    return render(request, 'kyc/complete_company_kyb.html', context)


@login_required
def add_company_director(request):
    """Add a director to company"""
    user = request.user
    
    if user.is_personal:
        messages.error(request, "This page is for business accounts only.")
        return redirect('kyc_status')
    
    # Check if user has permission
    if not (user.is_superuser or user.roles.filter(name='Admin').exists()):
        messages.error(request, "You don't have permission to add directors.")
        return redirect('kyc_status')
    
    try:
        company_profile = user.tenant.company_profile
    except CompanyProfile.DoesNotExist:
        messages.warning(request, "Please complete company profile first.")
        return redirect('edit_company_profile')
    
    if request.method == 'POST':
        form = CompanyDirectorForm(request.POST, request.FILES)
        if form.is_valid():
            director = form.save(commit=False)
            director.company_profile = company_profile
            director.save()
            
            messages.success(request, f"Director {director.first_name} {director.last_name} added successfully.")
            return redirect('complete_company_kyb')
    else:
        form = CompanyDirectorForm()
    
    context = {
        'form': form,
        'company_profile': company_profile,
    }
    return render(request, 'kyc/add_director.html', context)


@login_required
def edit_company_director(request, director_id):
    """Edit a company director"""
    user = request.user
    
    if user.is_personal:
        messages.error(request, "This page is for business accounts only.")
        return redirect('kyc_status')
    
    # Check if user has permission
    if not (user.is_superuser or user.roles.filter(name='Admin').exists()):
        messages.error(request, "You don't have permission to edit directors.")
        return redirect('kyc_status')
    
    try:
        company_profile = user.tenant.company_profile
    except CompanyProfile.DoesNotExist:
        messages.error(request, "Company profile not found.")
        return redirect('kyc_status')
    
    director = get_object_or_404(CompanyDirector, id=director_id, company_profile=company_profile)
    
    if request.method == 'POST':
        form = CompanyDirectorForm(request.POST, request.FILES, instance=director)
        if form.is_valid():
            form.save()
            messages.success(request, f"Director {director.first_name} {director.last_name} updated successfully.")
            return redirect('complete_company_kyb')
    else:
        form = CompanyDirectorForm(instance=director)
    
    context = {
        'form': form,
        'director': director,
        'company_profile': company_profile,
    }
    return render(request, 'kyc/edit_director.html', context)


@login_required
def delete_company_director(request, director_id):
    """Delete a company director"""
    user = request.user
    
    if user.is_personal:
        messages.error(request, "This page is for business accounts only.")
        return redirect('kyc_status')
    
    # Check if user has permission
    if not (user.is_superuser or user.roles.filter(name='Admin').exists()):
        messages.error(request, "You don't have permission to delete directors.")
        return redirect('kyc_status')
    
    try:
        company_profile = user.tenant.company_profile
    except CompanyProfile.DoesNotExist:
        messages.error(request, "Company profile not found.")
        return redirect('kyc_status')
    
    director = get_object_or_404(CompanyDirector, id=director_id, company_profile=company_profile)
    
    if request.method == 'POST':
        director_name = f"{director.first_name} {director.last_name}"
        director.delete()
        messages.success(request, f"Director {director_name} deleted successfully.")
        return redirect('complete_company_kyb')
    
    context = {
        'director': director,
        'company_profile': company_profile,
    }
    return render(request, 'kyc/delete_director_confirm.html', context)


# Helper functions
def send_kyc_notification_email(user, kyc_type):
    """Send email notification to admin when KYC is submitted"""
    try:
        subject = f"New {kyc_type} Submission - {user.username}"
        message = f"""
        A new {kyc_type} has been submitted for review.
        
        User: {user.username}
        Email: {user.email}
        Submitted at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        Please log in to the admin dashboard to review and approve.
        """
        
        # Get admin emails
        from documents.models import CustomUser
        admin_emails = CustomUser.objects.filter(
            is_superuser=True, is_active=True
        ).values_list('email', flat=True)
        
        if admin_emails:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(admin_emails),
                fail_silently=True,
            )
    except Exception as e:
        print(f"Error sending KYC notification email: {e}")


def send_kyb_notification_email(user, company_profile):
    """Send email notification to admin when KYB is submitted"""
    try:
        subject = f"New Company KYB Submission - {company_profile.company_name}"
        message = f"""
        A new Company KYB has been submitted for review.
        
        Company: {company_profile.company_name}
        Submitted by: {user.username}
        Email: {user.email}
        Submitted at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        Please log in to the admin dashboard to review and approve.
        """
        
        # Get admin emails
        from documents.models import CustomUser
        admin_emails = CustomUser.objects.filter(
            is_superuser=True, is_active=True
        ).values_list('email', flat=True)
        
        if admin_emails:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(admin_emails),
                fail_silently=True,
            )
    except Exception as e:
        print(f"Error sending KYB notification email: {e}")
