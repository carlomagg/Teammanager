# CRUD Functions for the Task model
# Also contains Reassign functionality

from datetime import date, datetime
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from documents.models import Task, CustomUser, Notification, UserNotification, File, Folder
from documents.forms import TaskForm, ReassignTaskForm
import logging, json

logger = logging.getLogger(__name__)

# List Tasks
@login_required
def task_list(request):
    # Validate tenant access
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        # return HttpResponseForbidden("You are not authorized for this company.")
        return render(request, 'error.html', {'message': 'You are not authorized for this company.'})

    category = request.GET.get('category', 'overall')
    
    # Filter tasks by tenant and user (assigned_to or created_by)
    tasks = Task.objects.filter(
        Q(assigned_to=request.user) | Q(created_by=request.user),
        tenant=request.tenant
    ).distinct()

    # if request.user.roles.filter(name=['Admin', 'HR']).exists():
    #     tasks = Task.objects.filter(tenant=request.tenant).distinct()
    # elif request.user.is_hod():
    #     department = request.user.department
    #     tasks = Task.objects.filter(tenant=request.tenant, assigned_to__department=department).distinct()
    # else:    

    reassign_form = ReassignTaskForm(user=request.user)
    
    # Apply category-specific filtering
    if category == 'personal':
        tasks = tasks.filter(assigned_to=request.user, created_by=request.user)
    elif category == 'corporate':
        tasks = tasks.filter(assigned_to=request.user).exclude(created_by=request.user)
    
    # Update overdue tasks for the current tenant
    overdue_tasks = Task.objects.filter(
        tenant=request.tenant,
        due_date__lt=date.today(),
        status__in=['pending', 'in_progress', 'on_hold'],
        assigned_to=request.user
    )
    if overdue_tasks.exists():
        logger.debug(f"Updating {overdue_tasks.count()} overdue tasks for tenant {request.tenant}")
        overdue_tasks.update(status='overdue')

    # Filter users by tenant and optionally by department
    users = CustomUser.objects.filter(tenant=request.tenant)
    if request.user.department:
        users = users.filter(department=request.user.department)
    
    logger.debug(f"Task list for tenant {request.tenant}: {tasks.count()} tasks, {users.count()} users")

    context = {
        'tasks': tasks,
        'status_labels': Task.STATUS_CHOICES,
        'today': date.today(),
        'user': request.user,
        'users': users,
        'category': category,
        'reassign_form': reassign_form,
    }
    return render(request, 'tasks/task_list.html', context)

def get_or_create_tasks_folder(user, tenant):
    """Helper to get or create a 'Tasks' folder for the tenant/user."""
    folder, created = Folder.objects.get_or_create(
        tenant=tenant,
        name="Tasks",
        defaults={
            'created_by': user,
            'is_public': True, # Or False, depending on desired visibility
            'description': "Folder for files uploaded via Tasks"
        }
    )
    return folder

# Create Task
@login_required
def create_task(request):
    # Ensure the user belongs to the current tenant
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.tenant = request.user.tenant
            task.save()
            form.save_m2m()

            # Create notification with link to task
            from documents.notification_helpers import create_task_notification
            create_task_notification(task, task.assigned_to.all(), action='created')
            
            # Handle direct file uploads
            uploaded_files = request.FILES.getlist('uploaded_files')
            if uploaded_files:
                tasks_folder = get_or_create_tasks_folder(request.user, request.tenant)
                for f in uploaded_files:
                    new_file = File.objects.create(
                        tenant=request.tenant,
                        folder=tasks_folder,
                        original_name=f.name,
                        uploaded_by=request.user
                    )
                    new_file.file.save(f.name, f, save=True)
                    task.documents.add(new_file)

            # Create notification for the task
            notif = Notification.objects.create(
                tenant=request.tenant,
                title=f"Task: {task.title}",
                message=task.description or "A new task has been assigned to you.",
                type=Notification.NotificationType.ALERT,
                expires_at=task.due_date,
                is_active=True
            )

            for assignee in task.assigned_to.all():
                UserNotification.objects.create(
                    tenant=request.tenant,
                    user=assignee,
                    notification=notif
                )
            return redirect('task_list')
    else:
        form = TaskForm(user=request.user)

    return render(request, 'tasks/create_task.html', {'form': form})

# Task detail
@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id, tenant=request.tenant)
    user = request.user
    if not (user in task.assigned_to.all() or task.created_by == request.user or request.user.is_hod()):
        return render(request, 'tasks/error.html', {'message': 'Access denied.'})
    return render(request, 'tasks/task_detail.html', {'task': task})

# Edit task
@login_required
def task_edit(request, task_id):
    # Validate tenant access
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")

    # Fetch task with tenant filter
    task = get_object_or_404(Task, id=task_id, tenant=request.user.tenant)

    # Check access permissions
    if not (task.created_by == request.user or request.user.is_hod()):
        logger.warning(f"Access denied for user {request.user.username} on task {task_id}")
        return render(request, 'tasks/error.html', {'message': 'Access denied.'})
    
    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, instance=task, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.tenant = request.tenant
            task.save()
            form.save_m2m()

            # Handle direct file uploads
            uploaded_files = request.FILES.getlist('uploaded_files')
            if uploaded_files:
                tasks_folder = get_or_create_tasks_folder(request.user, request.tenant)
                for f in uploaded_files:
                    new_file = File.objects.create(
                        tenant=request.tenant,
                        folder=tasks_folder,
                        original_name=f.name,
                        uploaded_by=request.user
                    )
                    new_file.file.save(f.name, f, save=True)
                    task.documents.add(new_file)

            logger.info(f"Task {task.id} edited by {request.user.username} in tenant {request.tenant}")

            from documents.notification_helpers import create_task_notification
            create_task_notification(task, task.assigned_to.all(), action='updated')
            
            return redirect('task_detail', task_id=task.id)
        
    else:
        form = TaskForm(instance=task, user=request.user)
        logger.debug(f"TaskForm initialized for task {task_id} with tenant: {request.tenant}")

    return render(request, 'tasks/edit_task.html', {'form': form, 'task': task})

# Update the status of a task
@csrf_exempt
@login_required
def update_task_status(request, task_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.") 
    task = get_object_or_404(Task, id=task_id, tenant=request.tenant)
    if not (request.user in task.assigned_to.all() or task.created_by == request.user or request.user.is_hod()):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_status = data.get('status')
            if new_status in dict(Task.STATUS_CHOICES):
                task.status = new_status
                if new_status == 'completed':
                    task.completed_at = timezone.now()
                task.tenant = request.tenant
                task.save()
                return JsonResponse({'success': True, 'status': task.status})
            return JsonResponse({'error': 'Invalid status'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Reassign task
@login_required
def reassign_task(request, task_id):
    # Fetch the task, ensuring it belongs to the current tenant
    task = get_object_or_404(Task, id=task_id, tenant=request.tenant)

    # Check permissions: only task creator or HOD can reassign
    if not (task.created_by == request.user or request.user.is_hod()):
        return JsonResponse({'error': 'Access denied.'}, status=403)

    if request.method == 'POST':
        try:
            # Extract assigned user IDs from POST request
            assigned_to_ids = request.POST.getlist('assigned_to')
            due_date_str = request.POST.get('due_date')

            # Validate inputs
            if not assigned_to_ids:
                return JsonResponse({'error': 'At least one assigned user is required.'}, status=400)
            if not due_date_str:
                return JsonResponse({'error': 'Due date is required.'}, status=400)

            # Parse and validate due date
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                if due_date < date.today():
                    return JsonResponse({'error': 'Due date cannot be in the past.'}, status=400)
            except ValueError:
                return JsonResponse({'error': 'Invalid due date format. Use YYYY-MM-DD.'}, status=400)

            # Fetch assigned users, ensuring they belong to the same tenant
            assigned_users = CustomUser.objects.filter(id__in=assigned_to_ids, tenant=request.tenant)
            if not assigned_users.exists() or len(assigned_users) != len(assigned_to_ids):
                return JsonResponse({'error': 'One or more selected users are invalid or not in the tenant.'}, status=400)

            # Update task fields
            task.due_date = due_date
            task.status = 'in_progress'
            task.save()

            # Update many-to-many relationship for assigned users
            task.assigned_to.clear()  # Clear existing assignments
            task.assigned_to.add(*assigned_users)  # Add new assignments
            # Create notification with link to task
            from documents.notification_helpers import create_task_notification
            create_task_notification(task, task.assigned_to.all(), action='reassigned')
            
            return redirect('task_list')

            return JsonResponse({'success': True, 'message': 'Task reassigned successfully.'})
        except ValidationError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=500)

    return JsonResponse({'error': 'Invalid request method. Use POST.'}, status=405)

# Delete Task
@login_required
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, tenant=request.tenant)
    if not (task.created_by == request.user or request.user.is_hod()):
        return render(request, 'tasks/error.html', {'message': 'Access denied.'})
    
    if request.method == 'POST':
        task.delete()
        return redirect('task_list')
    return render(request, 'tasks/confirm_delete.html', {'task': task})

# Remove document from task
@login_required
def delete_task_document(request, task_id, file_id):
    task = get_object_or_404(Task, id=task_id, tenant=request.tenant)
    document = get_object_or_404(File, id=file_id, tenant=request.tenant)
    if not (task.created_by == request.user or request.user.is_hod()) or document not in task.documents.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        task.documents.remove(document)
        # if not task.documents.exists():
        #     document.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Invalid request'}, status=400)