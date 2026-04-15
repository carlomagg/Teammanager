from django.contrib.auth.decorators import user_passes_test
from documents.models import CustomUser, Document, Folder, File, Task, Department, Team, Event, EventParticipant, StaffProfile, Notification, UserNotification
from documents.viewfuncs.mail_connection import get_email_smtp_connection
from raadaa import settings
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib.admin.models import LogEntry, CHANGE, ADDITION, DELETION
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail


@user_passes_test(is_admin)
def bulk_delete(request, model_name):
    """
    Deletes a list of objects of the given model_name.

    Requires the user to be an admin and the objects to belong to the same tenant.

    If the request method is not POST, returns HttpResponseForbidden with the message "Invalid request method."

    If the model_name is invalid, returns HttpResponseForbidden with the message "Invalid model name."

    If there is an error deleting the objects, returns HttpResponseForbidden with the message "Error deleting objects: <error message>".

    Otherwise, deletes the objects and redirects the user to the given redirect view.

    :param request: The request object containing the user and tenant information.
    :param model_name: The name of the model to delete objects from.
    :return: A HTTP response object indicating success or failure.
    """
    if request.method == "POST":
        # Validate tenant
        if request.user.tenant != request.tenant:
            return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

        # Map model names to actual model classes and their list view names
        model_mapping = {
            'customuser': (CustomUser, 'users_list'),
            'document': (Document, 'admin_document_list'),
            'folder': (Folder, 'admin_folder_list'),
            'file': (File, 'admin_file_list'),
            'task': (Task, 'admin_task_list'),
            'department': (Department, 'department_list'),
            'team': (Team, 'admin_team_list'),
            'event': (Event, 'event_list'),
            'eventparticipant': (EventParticipant, 'event_participant_list'),
            'staffprofile': (StaffProfile, 'staff_profile_list'),
            'notification': (Notification, 'admin_notification_list'),
            'usernotification': (UserNotification, 'user_notification_list'),
        }

        # Check if model_name is valid
        if model_name.lower() not in model_mapping:
            return HttpResponseForbidden("Invalid model name.")

        model_class, redirect_view = model_mapping[model_name.lower()]

        # Get IDs to delete
        ids = request.POST.getlist("ids")
        if not ids:
            return redirect(redirect_view)

        # Delete objects, ensuring they belong to the tenant
        try:
            model_class.objects.filter(id__in=ids, tenant=request.tenant).delete()
        except Exception as e:
            return HttpResponseForbidden(f"Error deleting objects: {str(e)}")

        return redirect(redirect_view)

    return HttpResponseForbidden("Invalid request method.")

@user_passes_test(is_admin)
def bulk_action_users(request):
    """
    Bulk activate or delete users.

    Parameters:
    action (str): Action to perform, either "activate" or "delete".
    ids (list): List of user IDs to perform the action on.

    Returns:
    HttpResponse: Redirects to the users list page if successful, or returns an HttpResponseForbidden if the admin does not belong to the company, or if the action is invalid, or if the IDs are invalid.

    Raises:
    Exception: If an error occurs while processing the action.
    """
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")
    
    if request.method != "POST":
        return HttpResponseForbidden("Invalid request method.")
    
    action = request.POST.get('action')
    ids = request.POST.getlist('ids')
    
    if not action or not ids:
        return redirect("users_list")  # Silently redirect if no action or IDs
    
    try:
        users = CustomUser.objects.filter(id__in=ids, tenant=request.tenant)
        if not users.exists():
            return HttpResponseForbidden("No valid users found for this company.")
        
        if action == "delete":
            users.delete()
            LogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(CustomUser).pk,
                object_id=None,
                object_repr="Multiple users",
                action_flag=CHANGE,
                change_message=f"Bulk deleted {len(ids)} users"
            )
        elif action == "activate":
            updated_count = users.update(is_active=True)
            LogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(CustomUser).pk,
                object_id=None,
                object_repr="Multiple users",
                action_flag=CHANGE,
                change_message=f"Bulk activated {updated_count} users"
            )
            # Send activation emails
            admin_user = request.user
            sender_provider = admin_user.email_provider
            sender_email = admin_user.email_address
            sender_password = admin_user.email_password
            if sender_email and sender_password:
                connection, error_message = get_email_smtp_connection(sender_provider, sender_email, sender_password)
                if settings.DEBUG:
                    base_domain = "localhost:8000"
                    protocol = "http"
                else:
                    base_domain = "teammanager.ng"
                    protocol = "https"
                login_url = f"{protocol}://{request.tenant.slug}.{base_domain}/accounts/login"
                
                for user in users:
                    subject = f"Account Approval: {user.username}"
                    message = f"""
                    Dear {user.username},

                    Your account has been activated. Please click the link below to log in:
                    {login_url}

                    Best regards,  
                    {admin_user.get_full_name() or admin_user.username}
                    """
                    try:
                        send_mail(
                            subject,
                            message,
                            sender_email,
                            [user.email],
                            connection=connection,
                        )
                    except Exception as e:
                        print(f"Failed to send email to {user.email}: {e}")
                        # Continue with other users even if one email fails
        else:
            return HttpResponseForbidden("Invalid action specified.")
    
    except Exception as e:
        return HttpResponseForbidden(f"Error processing action: {str(e)}")
    
    return redirect("users_list")