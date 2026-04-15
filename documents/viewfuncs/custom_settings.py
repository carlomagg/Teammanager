import logging
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from documents.forms import EmailConfigForm
from documents.models import CustomUser
from django.contrib.auth.decorators import login_required
from .mail_connection import get_email_smtp_connection
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash


logger = logging.getLogger(__name__)

@login_required
def custom_settings(request):
    user = CustomUser.objects.get(username=request.user.username, tenant=request.user.tenant)
    
    # Get subscription status - adjust based on your actual model structure
    # Assuming you have a subscription field or related model
    subscription_status = None
    
    # Option 1: If user has a subscription field directly
    if hasattr(user, 'subscription_status'):
        subscription_status = user.subscription_status
    
    # Option 2: If user has a related subscription model
    # try:
    #     subscription_status = user.subscription.status
    # except:
    #     subscription_status = 'No subscription'
    
    # Option 3: If it's a plan type
    # subscription_status = user.plan_type if user.plan_type else 'Free'
    
    context = {
        'user': user,
        'subscription_status': subscription_status or 'No active subscription',
    }
    
    return render(request, "settings/settings.html", context)
# def custom_settings(request):  # Add this view function for custom settings
#     user = CustomUser.objects.get(username=request.user.username, tenant=request.user.tenant)
#     return render(request, "settings/settings.html")

@login_required
def email_config(request):
    user = CustomUser.objects.get(username=request.user.username, tenant=request.user.tenant)
    if request.method == 'POST':
        email_config_form = EmailConfigForm(request.POST, instance=user)
        if email_config_form.is_valid():
            email_provider = email_config_form.cleaned_data["email_provider"]
            email_address = email_config_form.cleaned_data["email_address"]
            email_password = email_config_form.cleaned_data["email_password"]
            
            # Test SMTP connection
            connection, error_message = get_email_smtp_connection(email_provider, email_address, email_password)
            
            if connection:
                # Save credentials to the user's profile
                user = request.user
                user.email_provider = email_provider
                user.email_address = email_address
                user.set_smtp_password(email_password)  # Consider encrypting
                user.save()
                logger.info(f"Email config saved for {email_address}")
                return HttpResponseRedirect("/dashboard/email-config/success/")
            else:
                # Handle specific errors (e.g., Gmail 534)
                error_context = {"error": error_message}
                if "534" in error_message and email_provider == "gmail":
                    error_context["provider"] = "Gmail"
                    error_context["help_url"] = "https://support.google.com/mail/?p=InvalidSecondFactor"
                    error_context["message"] = (
                        "Gmail requires an app-specific password for third-party apps. "
                        "Please generate one in your Google Account settings and try again."
                    )
                elif email_provider == "zoho" and "authentication" in error_message.lower():
                    error_context["provider"] = "Zoho"
                    error_context["help_url"] = "https://www.zoho.com/mail/help/app-specific-passwords.html"
                    error_context["message"] = (
                        "Zoho requires an app-specific password for third-party apps. "
                        "Please generate one in your Zoho Account settings and try again."
                    )
                elif email_provider == "outlook" and "535" in error_message:
                    error_context["provider"] = "Outlook"
                    error_context["help_url"] = "https://support.microsoft.com/en-us/office/pop-imap-and-smtp-settings-for-outlook-com-d088b986-291d-42b8-9564-9c414e2aa040"
                    error_context["message"] = (
                        "Outlook requires an app-specific password for third-party apps when two-factor authentication is enabled. "
                        "Please generate one in your Microsoft Account settings and try again."
                    )
                elif email_provider == "yahoo" and "535" in error_message:
                    error_context["provider"] = "Yahoo"
                    error_context["help_url"] = "https://help.yahoo.com/kb/SLN15241.html"
                    error_context["message"] = (
                        "Yahoo requires an app-specific password for third-party apps when two-factor authentication is enabled. "
                        "Please generate one in your Yahoo Account settings and try again."
                    )
                elif email_provider == "icloud" and "535" in error_message:
                    error_context["provider"] = "iCloud"
                    error_context["help_url"] = "https://support.apple.com/en-us/HT204397"
                    error_context["message"] = (
                        "iCloud requires an app-specific password for third-party apps. "
                        "Please generate one in your Apple ID settings and try again."
                    )
                elif email_provider == "zeptomail":
                    error_context["provider"] = "ZeptoMail"
                    error_context["help_url"] = "https://www.zoho.com/zeptomail/help/smtp-home.html"
                    error_context["message"] = (
                        "Failed to connect to ZeptoMail. Please verify your SendMail Token and ensure the email address "
                        "(e.g., no-reply@teammanager.ng) is verified in your ZeptoMail dashboard. "
                        "Check if your account has sufficient credits or is not blocked."
                    )
                else:
                    error_context["provider"] = email_provider.capitalize()
                    error_context["help_url"] = ""  # Add generic help URL if needed
                    error_context["message"] = "Failed to connect to the email server. Please check your credentials or network."
                
                return render(request, "settings/email_config_error.html", error_context)
                # email_config_form.save()
                # return redirect('view_my_profile')
    else:
        email_config_form = EmailConfigForm(instance=user)
    return render(request, 'settings/email_config.html', {'email_config_form': email_config_form})

def email_config_success_view(request):
    return render(request, "settings/email_config_success.html")


# Change password for the current user
@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            request.user.must_reset_password = False
            request.user.save(update_fields=["must_reset_password"])
            return redirect('change_password_success')
    else:
        form = PasswordChangeForm(user=request.user)
    return render(request, 'settings/password_change.html', {'form': form})

def change_password_success(request):
    return render(request, "settings/password_change_success.html")