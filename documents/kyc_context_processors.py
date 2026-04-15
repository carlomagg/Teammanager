# documents/kyc_context_processors.py
"""
Context processor to add KYC/KYB status to all templates
Add this to settings.py TEMPLATES context_processors
"""

def kyc_status_context(request):
    """
    Add KYC/KYB status to template context
    Returns the actual status string for display in templates
    """
    context = {
        'kyc_status': None,
        'kyb_status': None,
        'kyc_verified': False,
        'kyb_verified': False,
        'kyc_pending': False,
        'kyb_pending': False,
        'show_kyc_reminder': False,
        'show_kyb_reminder': False,
    }
    
    if not request.user.is_authenticated:
        return context
    
    user = request.user
    
    # Check personal/staff KYC
    try:
        if user.is_personal:
            kyc = user.user_profile.kyc
            context['kyc_status'] = kyc.kyc_status
            context['kyc_verified'] = kyc.kyc_status == 'verified'
            context['kyc_pending'] = kyc.kyc_status in ['pending', 'submitted']
            context['show_kyc_reminder'] = kyc.kyc_status == 'pending'
        else:
            kyc = user.staff_profile.kyc
            context['kyc_status'] = kyc.kyc_status
            context['kyc_verified'] = kyc.kyc_status == 'verified'
            context['kyc_pending'] = kyc.kyc_status in ['pending', 'submitted']
            context['show_kyc_reminder'] = kyc.kyc_status == 'pending'
    except:
        # KYC not created yet
        context['kyc_status'] = 'pending'
        context['show_kyc_reminder'] = True
    
    # Check company KYB (for admins)
    if not user.is_personal and user.tenant:
        if user.is_superuser or user.roles.filter(name='Admin').exists():
            try:
                kyb = user.tenant.company_profile.kyb
                context['kyb_status'] = kyb.kyb_status
                context['kyb_verified'] = kyb.kyb_status == 'verified'
                context['kyb_pending'] = kyb.kyb_status in ['pending', 'submitted']
                context['show_kyb_reminder'] = kyb.kyb_status == 'pending'
            except:
                # KYB not created yet
                context['kyb_status'] = 'pending'
                context['show_kyb_reminder'] = True
    
    return context
