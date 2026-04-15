# CRUD Functions for the Folder model
# Also contains Share functionalities

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils import timezone
from documents.models import Folder, File
from documents.forms import FolderForm, FileUploadForm, FileUploadAnonForm
import re

# View Folders
@login_required
def folder_view(request, public_folder_id=None, personal_folder_id=None):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")

    # Get active tab, default to 'public'
    if request.effective_user.is_personal:
        active_tab = 'personal'
    else:
        active_tab = request.GET.get('tab', 'public') #if not request.user.is_personal else 'personal'
    all_pub = Folder.objects.filter(tenant=request.tenant, is_public=True)
    all_per = Folder.objects.filter(created_by=request.user, tenant=request.tenant, is_public=False)

    # Public tab context
    public_parent = None
    if public_folder_id:
        public_parent = get_object_or_404(
            Folder,
            id=public_folder_id,
            # created_by=request.user,
            tenant=request.tenant,
            is_public=True
        )
    public_folders = Folder.objects.filter(
        # created_by=request.user,
        parent=public_parent,
        tenant=request.tenant,
        is_public=True
    )
    public_files = File.objects.filter(
        folder=public_parent,
        # uploaded_by=request.user,
        tenant=request.tenant
    )

    # Personal tab context
    personal_parent = None
    if personal_folder_id:
        personal_parent = get_object_or_404(
            Folder,
            id=personal_folder_id,
            created_by=request.user,
            tenant=request.tenant,
            is_public=False
        )
    personal_folders = Folder.objects.filter(
        created_by=request.user,
        parent=personal_parent,
        tenant=request.tenant,
        is_public=False
    )
    personal_files = File.objects.filter(
        folder=personal_parent,
        uploaded_by=request.user,
        tenant=request.tenant,
        is_public = False
    )
    # personal_files_2 = File.objects.filter(
    #     folder=personal_parent,
    #     # uploaded_by=request.user,
    #     tenant=request.tenant,
    #     is_public=False
    # )
    # personal_files = personal_files_1.union(personal_files_2)

    now = timezone.now()
    # today = now.date()

    # Generate shareable links for files
    for file in public_files:
        file.shareable_link = request.build_absolute_uri(file.get_shareable_link()) if file.is_shared else None
    for file in personal_files:
        file.shareable_link = request.build_absolute_uri(file.get_shareable_link()) if file.is_shared else None

    # Generate shareable links for folders
    for folder in public_folders:
        folder.shareable_link = request.build_absolute_uri(folder.get_shareable_link()) if folder.is_shared else None
        if folder.share_time_end and folder.share_time_end < now:
            folder.is_shared = False
            # folder.save()
            # folder.shareable_link = None
    for folder in personal_folders:
        folder.shareable_link = request.build_absolute_uri(folder.get_shareable_link()) if folder.is_shared else None
        if folder.share_time_end and folder.share_time_end < now:
            folder.is_shared = False
            # folder.save()
            # folder.shareable_link = None


    folder_form = FolderForm(initial={'parent': public_parent if active_tab == 'public' else personal_parent})
    file_form = FileUploadForm()

    return render(request, 'folder/folders.html', {
        'active_tab': active_tab,
        'public_parent': public_parent,
        'public_folders': public_folders,
        'public_files': public_files,
        'personal_parent': personal_parent,
        'personal_folders': personal_folders,
        'personal_files': personal_files,
        'folder_form': folder_form,
        'file_form': file_form,
        'all_pub': all_pub,
        'all_per': all_per,
    })

# Create Folders
@login_required
def create_folder(request):
    if request.method == 'POST':
        form = FolderForm(request.POST)
        if request.effective_user.is_personal:
            active_tab = 'personal'
        else:
            active_tab = request.POST.get('tab')  # Changed from request.GET to request.POST
        if form.is_valid():
            folder = form.save(commit=False)
            folder.created_by = request.user
            folder.tenant = request.tenant
            
            if active_tab == 'public':
                folder.is_public = True
            else:
                folder.is_public = False
                
            # Validate that the user belongs to the same tenant
            if folder.created_by.tenant != request.tenant:
                return JsonResponse({'success': False, 'errors': 'Unauthorized: User does not belong to this company.'}, status=403)
            
            # Get parent ID from POST data, not GET
            parent_id = request.POST.get('parent')
            print(f"Parent ID: {parent_id}, Active tab: {active_tab}")
            
            if parent_id and parent_id != 'None' and parent_id != '':
                try:
                    folder.parent = Folder.objects.get(id=parent_id, tenant=request.tenant)
                except Folder.DoesNotExist:
                    return JsonResponse({'success': False, 'errors': 'Parent folder not found.'}, status=400)
            
            folder.save()
            # return JsonResponse({'success': True, 'redirect_url': f'/folders/?tab={active_tab}'})
            if folder.parent:
                if folder.is_public:
                    url_name = 'folder_view_public'
                    kwargs = {'public_folder_id': folder.parent.id}
                else:
                    url_name = 'folder_view_personal'
                    kwargs = {'personal_folder_id': folder.parent.id}
            else:
                url_name = 'folder_view'
                kwargs = {}

            # return redirect(f"{reverse(url_name, kwargs=kwargs)}?tab={active_tab}")
            return JsonResponse({'success': True, 'redirect_url': f'{reverse(url_name, kwargs=kwargs)}?tab={active_tab}'})
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    
    return JsonResponse({'success': False, 'errors': 'Invalid request method.'}, status=400)

# Delete Folder
@login_required
def delete_folder(request, folder_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    folder = get_object_or_404(Folder, id=folder_id, created_by=request.user, tenant=request.tenant)
    if folder.created_by != request.user:
        return HttpResponseForbidden("You are not authorized to delete this folder.")
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
        url_name = 'folder_view'
        kwargs = {}
    folder.delete()
    return JsonResponse({'success': True, 'redirect_url': f'{reverse(url_name, kwargs=kwargs)}?tab={active_tab}'})
    # return JsonResponse({'success': True})
    # return JsonResponse({'success': False, 'errors': form.errors}, status=400)


# Folder Sharing Function
@login_required
def enable_folder_sharing(request, folder_id):
    # View to toggle the sharing status of a file
    folder = get_object_or_404(Folder, id=folder_id, tenant=request.user.tenant)
    
    # Optional: Add permission checks (e.g., only allow certain users to toggle sharing)
    # if public_file.created_by != request.user:
    #     # return HttpResponseForbidden("You do not have permission to modify this file.")
    #     raise PermissionDenied("You do not have permission to modify this file.")

    if request.method == 'POST':
        end_date = request.POST.get('end_date')  # Already handled; could be empty string or None
        share_subfolders = 'share_folders' in request.POST  # True if checked, False otherwise
        share_files = 'share_files' in request.POST  # True if checked, False otherwise

        folder.is_shared = not folder.is_shared
        folder.share_time = timezone.now()
        folder.share_time_end = end_date if end_date else None
        folder.shared_by = request.user
        folder.share_subfolders = share_subfolders
        folder.share_files = share_files

        folder.save()
        if end_date:
            folder.share_time_end = end_date
        if share_subfolders:
            folder.share_subfolders = True
            for subfolder in Folder.objects.filter(parent=folder, tenant=request.tenant):
                subfolder.is_shared = True
                subfolder.share_time = timezone.now()
                subfolder.share_time_end = end_date if end_date else None
                subfolder.shared_by = request.user
                subfolder.share_subfolders = share_subfolders
                subfolder.share_files = share_files
                subfolder.save()
        if share_files:
            for file in folder.files.all():  # Adjust based on your model
                    file.is_shared = True
                    file.share_time = timezone.now()
                    file.share_time_end = end_date if end_date else None
                    file.shared_by = request.user
                    file.save()
        # folder.shared_by = request.user
        # folder.save()
        if request.effective_user.is_personal:
            active_tab = 'personal'
        else:
            active_tab = request.GET.get('tab', 'public')
        
    # Determine the correct URL based on folder.is_public and active_tab
    if folder.parent:
        if folder.is_public:
            url_name = 'folder_view_public'
            kwargs = {'public_folder_id': folder.parent.id}
        else:
            url_name = 'folder_view_personal'
            kwargs = {'personal_folder_id': folder.parent.id}
    else:
        url_name = 'folder_view'
        kwargs = {}

    # return redirect(f"{reverse(url_name, kwargs=kwargs)}?tab={active_tab}")
    return JsonResponse({"success": True, "folder_id": folder.id})

# Display Shared Folder
def shared_folder_view(request, token):
    # Retrieve the folder by share token
    folder = get_object_or_404(Folder, share_token=token, is_shared=True)
    folders = Folder.objects.filter(parent=folder, tenant=request.tenant)
    files = File.objects.filter(
        folder=folder,
        # uploaded_by=request.user,
        tenant=request.tenant
    )
    file_form = FileUploadAnonForm()
    
    # Optional: Add additional checks (e.g., tenant status, file availability)
    if not folder.name:
        return HttpResponseForbidden("File not available.")
    
    for fold in folders:
        fold.is_shared = True
        fold.shareable_link = request.build_absolute_uri(fold.get_shareable_link())
        fold.share_time = timezone.now()
        fold.share_time_end = fold.parent.share_time_end
        fold.shared_by = fold.parent.shared_by
        fold.save()
    
    context = {
        'folder': folder,
        'folders': folders if folder.share_subfolders else [],
        'files': files if folder.share_files else [],
        'file_form': file_form,
        # 'file_url': file.file.url,  # URL to access the file
    }
    return render(request, 'folder/shared_folder_view.html', context)

# Rename Folder
@login_required
def rename_folder(request, folder_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    folder = get_object_or_404(Folder, id=folder_id, created_by=request.user, tenant=request.tenant)
    if folder.created_by != request.user:
        return HttpResponseForbidden("You are not authorized to rename this folder.")
    if request.method == 'POST':
        new_name = request.POST.get('name', '').strip()

        # Validate the new name
        if not new_name:
            return JsonResponse({'success': False, 'error': 'Folder name cannot be empty.'}, status=400)

        if len(new_name) > 255:
            return JsonResponse({'success': False, 'error': 'Folder name is too long.'}, status=400)

        # Validate name format (e.g., no special characters)
        if not re.match(r'^[\w\s\-\.]+$', new_name):
            return JsonResponse({'success': False, 'error': 'Folder name contains invalid characters.'}, status=400)

        # Check for duplicate folder names within the tenant
        if Folder.objects.filter(tenant=request.tenant, name=new_name).exclude(id=folder.id).exists():
            return JsonResponse({'success': False, 'error': 'A folder with this name already exists.'}, status=400)

        try:
            with transaction.atomic():
                folder.name = new_name
                folder.save()
                return JsonResponse({'success': True, 'new_name': folder.name})
        except ValidationError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=400)


# Move Folder
@login_required
def move_folder(request, folder_id):
    if not hasattr (request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    folder = get_object_or_404(Folder, id=folder_id, created_by=request.user, tenant=request.tenant)
    if request.method == 'POST':
        if request.effective_user.is_personal:
            active_tab = 'personal'
        else:
            active_tab = request.POST.get('tab')
        if folder.is_public != (active_tab == 'public'):
            return JsonResponse({'success': False, 'errors': {'general': 'Invalid tab context'}})
        new_parent_id = request.POST.get('new_parent_id')
        if new_parent_id:
            folder.parent = Folder.objects.get(id=new_parent_id, tenant=request.tenant)
            folder.save()

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
            url_name = 'folder_view'
            kwargs = {}
        return JsonResponse({'success': True, 'redirect_url': f'{reverse(url_name, kwargs=kwargs)}?tab={active_tab}'})
        # return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)