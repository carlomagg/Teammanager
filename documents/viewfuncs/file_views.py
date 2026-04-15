# CRUD Functions for the File Model
# Also contains Share functionalities

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.urls.base import reverse
from documents.models import Folder, File
from documents.forms import FileUploadForm, FileUploadAnonForm, FolderForm
import re

# Upload File in Folders for known user
@login_required
def upload_file(request, public_folder_id=None, personal_folder_id=None):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return JsonResponse({"success": False, "errors": "You are not authorized for this company."}, status=403)

    active_tab = request.POST.get('tab')  # Changed from request.GET to request.POST
    
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.save(commit=False)
            uploaded_file.uploaded_by = request.user
            uploaded_file.tenant = request.tenant
            uploaded_file.original_name = request.FILES['file'].name
            
            # Get folder from POST data or URL parameters
            folder_id = request.POST.get('folder')
            if folder_id and folder_id != 'None' and folder_id != '':
                try:
                    uploaded_file.folder = Folder.objects.get(id=folder_id, tenant=request.tenant)
                    uploaded_file.is_public = uploaded_file.folder.is_public
                except Folder.DoesNotExist:
                    return JsonResponse({"success": False, "errors": "Folder not found."}, status=400)
            
            uploaded_file.save()
            folder = uploaded_file.folder
            if folder.parent:
                if folder.is_public:
                    url_name = 'folder_view_public'
                    kwargs = {'public_folder_id': folder.parent.id}
                    active_tab = 'public'
                else:
                    url_name = 'folder_view_personal'
                    kwargs = {'personal_folder_id': folder.parent.id}
                    active_tab = 'personal'
            else:
                if folder.is_public:
                    url_name = 'folder_view_public'
                    kwargs = {'public_folder_id': folder.id}
                    active_tab = 'public'
                else:
                    url_name = 'folder_view_personal'
                    kwargs = {'personal_folder_id': folder.id}
                    active_tab = 'personal'
            # return JsonResponse({"success": True, "redirect_url": f'/folders/?tab={active_tab}'})
            return JsonResponse({'success': True, 'redirect_url': f'{reverse(url_name, kwargs=kwargs)}?tab={active_tab}'})
        else:
            return JsonResponse({"success": False, "errors": form.errors}, status=400)
    
    return JsonResponse({"success": False, "errors": "Invalid request method."}, status=400)

# Upload File in Folders for anonymous users (when folder is shared)
def upload_file_anon(request, public_folder_id=None, personal_folder_id=None):
    # Check tenant authorization first
    # if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
    #     return HttpResponseForbidden("You are not authorized for this tenant.")

    # active_tab = request.GET.get('tab', 'public')
    print("Public folder id:", public_folder_id)
    public_parent_folder = None
    personal_parent_folder = None
    if public_folder_id:
        public_parent_folder = Folder.objects.get(
            id=public_folder_id, 
            tenant=request.tenant, 
            is_public=True
        )
    elif personal_folder_id:
        personal_parent_folder = Folder.objects.get(
            id=personal_folder_id,
            tenant=request.tenant, 
            is_public=False
        )
    else:
        folder_id = None

    if request.method == 'POST':
        form = FileUploadAnonForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.save(commit=False)
            # uploaded_file.uploaded_by = None
            uploaded_file.anon_name = form.cleaned_data["anon_name"]
            # print("uploaded by", uploaded_file.uploaded_by.username)
            print("uploaded by: ", form.cleaned_data["anon_name"])
            uploaded_file.tenant = request.tenant
            uploaded_file.original_name = request.FILES['file'].name
            if public_parent_folder:
                uploaded_file.folder = public_parent_folder  # Assign to the current folder
            else:
                uploaded_file.folder = personal_parent_folder
            if uploaded_file.folder.is_public:
                uploaded_file.is_public = True
            uploaded_file.save()
            
            return JsonResponse({"success": True, "file_id": uploaded_file.id})
        else:
            # If form is invalid, return errors as JSON
            return JsonResponse({"success": False, "errors": form.errors})
    else:
        # GET request - initialize empty form
        form = FileUploadAnonForm()
        # Render a simple upload form for anonymous users
        return render(request, 'folder/upload_anon.html', {
            'file_form': form,
            'public_parent': public_parent_folder,
            'personal_parent': personal_parent_folder,
            'folder': public_parent_folder or personal_parent_folder,
        })

# File Sharing Function
@login_required
def enable_file_sharing(request, file_id):
    # View to toggle the sharing status of a file
    file = get_object_or_404(File, id=file_id, tenant=request.user.tenant)
    end_date = request.POST.get('end_date')

    if request.method == 'POST':
        file.is_shared = not file.is_shared
        file.share_time = timezone.now()
        if end_date:
            file.share_time_end = end_date
        file.shared_by = request.user
        file.save()
        active_tab = request.GET.get('tab', 'public')
        
    # Determine the correct URL based on file.is_public and active_tab
    if file.folder:
        if file.is_public:
            url_name = 'folder_view_public'
            kwargs = {'public_folder_id': file.folder.id}
        else:
            url_name = 'folder_view_personal'
        kwargs = {'personal_folder_id': file.folder.id}
    else:
        url_name = 'folder_view'
        kwargs = {}

    # return redirect(f"{reverse(url_name, kwargs=kwargs)}?tab={active_tab}")
    return JsonResponse({"success": True, "file_id": file.id})

# Display shared file
def shared_file_view(request, token):
    # Retrieve the file by share token
    file = get_object_or_404(File, share_token=token, is_shared=True)
    
    # Optional: Add additional checks (e.g., tenant status, file availability)
    if not file.file:
        return HttpResponseForbidden("File not available.")
    
    context = {
        'file': file,
        'file_url': file.file.url,  # URL to access the file
    }
    return render(request, 'folder/shared_file_view.html', context)

# Delete File
@login_required
def delete_file(request, file_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    file = get_object_or_404(File, id=file_id, uploaded_by=request.user, tenant=request.tenant)
    if file.uploaded_by != request.user:
        return HttpResponseForbidden("You are not authorized to delete this file.")
    file.delete()
    return JsonResponse({'success': True})
    # return JsonResponse({'success': False, 'errors': form.errors}, status=400)

# Rename File
@login_required
def rename_file(request, file_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    file = get_object_or_404(File, id=file_id, uploaded_by=request.user, tenant=request.tenant)
    if request.method == 'POST':
        new_name = request.POST.get('name')
        # Validate the new name
        if not new_name:
            return JsonResponse({'success': False, 'error': 'File name cannot be empty.'}, status=400)

        if len(new_name) > 255:
            return JsonResponse({'success': False, 'error': 'File name is too long.'}, status=400)

        # Validate name format (e.g., no special characters)
        if not re.match(r'^[\w\s\-\.]+$', new_name):
            return JsonResponse({'success': False, 'error': 'File name contains invalid characters.'}, status=400)

        try:
            with transaction.atomic():
                file.original_name = new_name
                file.save()
                return JsonResponse({'success': True, 'new_name': file.original_name})
        except ValidationError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=400)

# Move File
@login_required
def move_file(request, file_id):
    if not hasattr (request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    file = get_object_or_404(File, id=file_id, uploaded_by=request.user, tenant=request.tenant)
    if request.method == 'POST':
        active_tab = request.POST.get('tab')
        if file.is_public != (active_tab == 'public'):
            return JsonResponse({'success': False, 'errors': {'general': 'Invalid tab context'}})
        new_folder_id = request.POST.get('new_folder_id')
        if new_folder_id:
            file.folder = Folder.objects.get(id=new_folder_id, tenant=request.tenant)
            file.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)



# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC FILE UPLOAD (No login required, no specific folder needed)
# ══════════════════════════════════════════════════════════════════════════════

def public_file_upload(request, tenant_slug):
    """
    Public file upload view - accessible without login.
    Creates a general submission folder if needed.
    """
    from tenants.models import Tenant
    from django.core.mail import send_mail
    from django.conf import settings
    from documents.models import Notification, UserNotification, CustomUser
    from django.contrib.contenttypes.models import ContentType
    
    tenant = get_object_or_404(Tenant, slug=tenant_slug)
    
    if request.method == 'POST':
        form = FileUploadAnonForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Get the first admin/staff user to assign as folder creator
                folder_creator = CustomUser.objects.filter(
                    tenant=tenant,
                    is_staff=True, 
                    is_active=True
                ).first()
                
                if not folder_creator:
                    # Fallback to tenant admin
                    folder_creator = tenant.admin
                
                if not folder_creator:
                    raise Exception("No admin user found to create folder")
                
                # Get or create a "Public Submissions" folder
                public_folder, created = Folder.objects.get_or_create(
                    tenant=tenant,
                    name='Public Submissions',
                    is_public=True,
                    defaults={
                        'is_shared': True,
                        'description': 'Files submitted through Quick Services',
                        'created_by': folder_creator
                    }
                )
                
                uploaded_file = form.save(commit=False)
                uploaded_file.anon_name = form.cleaned_data["anon_name"]
                uploaded_file.tenant = tenant
                uploaded_file.original_name = request.FILES['file'].name
                uploaded_file.folder = public_folder
                uploaded_file.is_public = True
                uploaded_file.save()
                
                # Create notification for staff
                notification = Notification.objects.create(
                    tenant=tenant,
                    title=f"New File from {uploaded_file.anon_name}",
                    message=f"File '{uploaded_file.original_name}' has been uploaded",
                    type=Notification.NotificationType.ALERT,
                    content_type=ContentType.objects.get_for_model(File),
                    object_id=uploaded_file.id,
                    link=f'/folders/'
                )
                
                # Notify all staff members
                staff_users = CustomUser.objects.filter(
                    tenant=tenant,
                    is_staff=True, 
                    is_active=True
                )
                for staff_user in staff_users:
                    UserNotification.objects.create(
                        tenant=tenant,
                        user=staff_user,
                        notification=notification
                    )
                
                # Send email notification
                try:
                    admin_emails = staff_users.values_list('email', flat=True)
                    if admin_emails:
                        send_mail(
                            subject=f'New File Upload from {uploaded_file.anon_name}',
                            message=f'A new file has been uploaded:\n\nFile: {uploaded_file.original_name}\nFrom: {uploaded_file.anon_name}\nFolder: Public Submissions',
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=list(admin_emails),
                            fail_silently=True,
                        )
                except Exception as e:
                    print(f"Email notification failed: {e}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({"success": True, "file_id": uploaded_file.id})
                else:
                    messages.success(request, 'Your file has been uploaded successfully!')
                    return redirect('quick_services')
                    
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({"success": False, "errors": str(e)})
                else:
                    messages.error(request, f'An error occurred: {str(e)}')
        else:
            # Form is invalid
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        # GET request - show form
        form = FileUploadAnonForm()
    
    return render(request, 'folder/public_file_upload.html', {
        'file_form': form,
        'tenant': tenant,
    })
