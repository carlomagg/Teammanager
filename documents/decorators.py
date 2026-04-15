"""
Custom decorators for permission-based access control.
"""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages


def support_dashboard_permission_required(view_function):
    """
    Decorator to check if user has permission to view the Customer Support dashboard.
    Allows superusers and users with 'view_support_dashboard' permission.
    """
    @wraps(view_function)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        user = request.user
        
        # Superusers always have access
        if user.is_superuser:
            return view_function(request, *args, **kwargs)
        
        # Check for specific permission
        if user.has_perm('documents.view_support_dashboard'):
            return view_function(request, *args, **kwargs)
        
        # User doesn't have permission
        messages.error(request, "You don't have permission to access the Customer Support dashboard.")
        return redirect('home')
    
    return wrapped_view


def support_update_permission_required(view_function):
    """
    Decorator to check if user has permission to update Customer Support activities.
    Allows superusers and users with 'update_support_activity' permission.
    """
    @wraps(view_function)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        user = request.user
        
        # Superusers always have access
        if user.is_superuser:
            return view_function(request, *args, **kwargs)
        
        # Check for specific permission
        if user.has_perm('documents.update_support_activity'):
            return view_function(request, *args, **kwargs)
        
        # User doesn't have permission
        messages.error(request, "You don't have permission to update Customer Support activities.")
        return redirect('support_dashboard')
    
    return wrapped_view


def kyc_verification_permission_required(view_function):
    """
    Decorator to check if user has permission to view/access KYC/KYB.
    Only allows superusers to access the KYC dashboard and approval functions.
    """
    @wraps(view_function)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        user = request.user
        
        # Only superusers can access KYC dashboard
        if user.is_superuser:
            return view_function(request, *args, **kwargs)
        
        # User doesn't have permission - render 403 page
        from django.shortcuts import render
        return render(request, '403.html', {
            'message': 'Only super administrators can access the KYC/KYB verification dashboard.'
        }, status=403)
    
    return wrapped_view
