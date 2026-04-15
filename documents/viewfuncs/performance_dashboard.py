from datetime import timedelta
import logging
from django.http import HttpResponseForbidden
from django.shortcuts import render
from documents.models import CustomUser, Department, Task
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import F



logger = logging.getLogger(__name__)

@login_required
def performance_dashboard(request):
    # Validate tenant access
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")

    user = request.user
    category = request.GET.get('category', 'overall')
    
    # Filter tasks by tenant and assigned_to user
    tasks = Task.objects.filter(tenant=request.user.tenant, assigned_to=user)
    if category == 'personal':
        tasks = tasks.filter(created_by=user)
    elif category == 'corporate':
        tasks = tasks.exclude(created_by=user)
    
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='completed').count()
    completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    year_ago = now - timedelta(days=365)

    weekly_completed = tasks.filter(status='completed', completed_at__gte=week_ago).count()
    monthly_completed = tasks.filter(status='completed', completed_at__gte=month_ago).count()
    yearly_completed = tasks.filter(status='completed', completed_at__gte=year_ago).count()

    overdue_tasks = tasks.filter(status='overdue', due_date__lt=now).count()

    performance_score = completion_percentage - (overdue_tasks * 10)
    performance_score = max(0, min(100, performance_score))

    context = {
        'category': category,
        'completion_percentage': round(completion_percentage, 2),
        'weekly_completed': weekly_completed,
        'monthly_completed': monthly_completed,
        'yearly_completed': yearly_completed,
        'overdue_tasks': overdue_tasks,
        'performance_score': round(performance_score, 2),
    }
    return render(request, 'dashboard/performance_dashboard.html', context)

@login_required
def hod_performance_dashboard(request):
    # Validate tenant access
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    
    user = request.user
    if not user.is_hod():
        return render(request, 'tasks/error.html', {'message': 'Access denied. HOD role required.'})

    # Get all departments where user is HOD
    departments = Department.objects.filter(hod=user, tenant=request.tenant)
    if not departments.exists():
        return render(request, 'tasks/error.html', {'message': 'No departments assigned to you.'})

    # Get department filter from query parameter
    selected_department_id = request.GET.get('department_id', 'all')
    
    # Filter departments if a specific one is selected
    if selected_department_id != 'all':
        try:
            selected_department = departments.get(id=selected_department_id)
            departments_to_show = [selected_department]
        except Department.DoesNotExist:
            departments_to_show = departments
            selected_department_id = 'all'
    else:
        departments_to_show = departments

    # Get all users from the selected department(s)
    department_users = CustomUser.objects.filter(
        department__in=departments_to_show, 
        tenant=request.tenant
    ).select_related('department')
    
    users_ids = [u.id for u in department_users]

    # Get user filter from query parameter (optional)
    selected_user_id = request.GET.get('user_id', 'all')
    
    # Base query: corporate tasks (created by department members, not personal)
    tasks = Task.objects.filter(
        created_by__in=users_ids, 
        tenant=request.tenant
    ).exclude(created_by=F('assigned_to')).select_related('created_by', 'assigned_to')

    # Filter by selected user if specified
    if selected_user_id != 'all':
        tasks = tasks.filter(assigned_to__id=selected_user_id)

    # Department-wide or user-specific metrics
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='completed').count()
    completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    # Per-user metrics for the table
    user_metrics = []
    for dept_user in department_users:
        user_tasks = Task.objects.filter(
            created_by__in=users_ids,
            assigned_to=dept_user,
            tenant=request.tenant
        ).exclude(created_by=F('assigned_to')).select_related('assigned_to')
        
        user_total_tasks = user_tasks.count()
        user_completed_tasks = user_tasks.filter(status='completed').count()
        user_completion_percentage = (user_completed_tasks / user_total_tasks * 100) if user_total_tasks > 0 else 0
        
        user_metrics.append({
            'user_id': dept_user.id,
            'full_name': dept_user.get_full_name() or dept_user.username,
            'department': dept_user.department.name if dept_user.department else 'N/A',
            'total_tasks': user_total_tasks,
            'completed_tasks': user_completed_tasks,
            'completion_percentage': round(user_completion_percentage, 2),
        })

    context = {
        'departments': departments,
        'selected_department_id': selected_department_id,
        'completion_percentage': round(completion_percentage, 2),
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'user_metrics': user_metrics,
        'department_users': department_users,
        'selected_user_id': selected_user_id,
    }
    return render(request, 'dashboard/hod_performance_dashboard.html', context)