from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F, DecimalField, Min, Max
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.utils import timezone
from datetime import timedelta
from documents.models import Contact
from .models import Opportunity, Product, PipelineStage, Activity
from .forms import OpportunityForm, ProductForm, ActivityForm
from .mixins import CRMCreateViewMixin, CRMUpdateViewMixin, CRMDeleteViewMixin
from cities_light.models import City, Country


@login_required
@never_cache
def crm_dashboard(request):
    """
    Role-based CRM dashboard with overview metrics.
    - Superuser: System-wide data with tenant rankings
    - Tenant users: Tenant-specific data
    - Personal users: Personal data only
    """
    tenant = request.effective_tenant
    user = request.effective_user
    
    # Get filter parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    category_filter = request.GET.get('category')
    stage_filter = request.GET.get('stage')
    industry_filter = request.GET.get('industry')
    source_filter = request.GET.get('source')
    deal_size_filter = request.GET.get('deal_size')
    
    # Determine user role and get base queryset
    is_superuser = user.is_staff
    
    if is_superuser:
        # Superuser sees all opportunities (tenants + personal users)
        opportunities = Opportunity.objects.all()
        dashboard_type = 'superuser'
    elif tenant:
        # Tenant user sees only their tenant's data
        opportunities = Opportunity.objects.filter(tenant=tenant)
        dashboard_type = 'tenant'
    else:
        # Personal user sees only their own data
        opportunities = Opportunity.objects.filter(tenant=None, created_by=user)
        dashboard_type = 'personal'
    
    # Apply filters
    if date_from:
        opportunities = opportunities.filter(created_at__gte=date_from)
    if date_to:
        opportunities = opportunities.filter(created_at__lte=date_to)
    if category_filter:
        opportunities = opportunities.filter(category=category_filter)
    if stage_filter:
        opportunities = opportunities.filter(stage_id=stage_filter)
    if industry_filter:
        opportunities = opportunities.filter(industry=industry_filter)
    if source_filter:
        opportunities = opportunities.filter(source=source_filter)
    if deal_size_filter:
        opportunities = opportunities.filter(deal_size=deal_size_filter)
    
    # Common metrics for all dashboard types
    total_leads = opportunities.filter(category='Lead').count()
    total_deals = opportunities.filter(category='Deal').count()
    total_customers = opportunities.filter(category='Customer').count()
    total_opportunities = opportunities.count()
    
    # Deal value metrics
    deal_metrics = opportunities.filter(category='Deal').aggregate(
        total_estimated=Sum('estimated_amount'),
        total_actual=Sum('actual_amount')
    )
    total_estimated_value = deal_metrics['total_estimated'] or 0
    total_actual_value = deal_metrics['total_actual'] or 0
    
    # Recent opportunities
    recent_opportunities = opportunities.select_related(
        'stage', 'assigned_to', 'tenant'
    ).order_by('-created_at')[:10]
    
    # Opportunities by stage
    opportunities_by_stage = opportunities.values(
        'stage__name', 'stage__category'
    ).annotate(count=Count('id')).order_by('stage__category', 'stage__order')
    
    # Opportunities by deal size
    opportunities_by_size = opportunities.exclude(
        deal_size=''
    ).values('deal_size').annotate(
        count=Count('id'),
        total_value=Sum('estimated_amount')
    ).order_by('-total_value')
    
    # NEW METRICS: Partners, Referrals, Contractors, Contacts
    total_partners = opportunities.filter(partner_contact__isnull=False).values('partner_contact').distinct().count()
    total_referrals = opportunities.filter(source='Referral').count()
    total_contractors = opportunities.filter(contractor_contact__isnull=False).values('contractor_contact').distinct().count()
    
    # Total contacts in system
    if is_superuser:
        total_contacts = Contact.objects.all().count()
    elif tenant:
        total_contacts = Contact.objects.filter(tenant=tenant).count()
    else:
        total_contacts = Contact.objects.filter(tenant=None, created_by=user).count()
    
    # Companies by Size breakdown
    companies_by_size = opportunities.exclude(
        company_size=''
    ).values('company_size').annotate(
        count=Count('id'),
        total_value=Sum('estimated_amount')
    ).order_by('company_size')
    
    # CUSTOMER CATEGORIES
    today = timezone.now().date()
    three_months_ago = today - timedelta(days=90)
    
    # New Customers: First closed-won within last 3 months
    new_customers = opportunities.filter(
        category='Customer',
        stage__name='Closed Won'
    ).values('company_name').annotate(
        first_won_date=Min('created_at')
    ).filter(
        first_won_date__gte=three_months_ago
    ).count()
    
    # Top 10 Customers by LTV (Lifetime Value)
    top_customers_by_value = opportunities.filter(
        category='Customer',
        stage__name='Closed Won'
    ).values('company_name').annotate(
        total_value=Sum('actual_amount')
    ).order_by('-total_value')[:10]
    
    # Expanding Customers: >1 closed-won and increasing spend
    # Compare current year vs previous year
    current_year = today.year
    previous_year = current_year - 1
    
    expanding_customers = []
    customer_companies = opportunities.filter(
        category='Customer',
        stage__name='Closed Won'
    ).values('company_name').annotate(
        deal_count=Count('id')
    ).filter(deal_count__gt=1)
    
    for customer in customer_companies:
        company = customer['company_name']
        current_year_spend = opportunities.filter(
            company_name=company,
            category='Customer',
            stage__name='Closed Won',
            created_at__year=current_year
        ).aggregate(total=Sum('actual_amount'))['total'] or 0
        
        previous_year_spend = opportunities.filter(
            company_name=company,
            category='Customer',
            stage__name='Closed Won',
            created_at__year=previous_year
        ).aggregate(total=Sum('actual_amount'))['total'] or 0
        
        if current_year_spend > previous_year_spend and previous_year_spend > 0:
            expanding_customers.append({
                'company_name': company,
                'current_year_spend': current_year_spend,
                'previous_year_spend': previous_year_spend,
                'growth': current_year_spend - previous_year_spend
            })
    
    expanding_customers = sorted(expanding_customers, key=lambda x: x['growth'], reverse=True)[:10]
    
    # Renewing Customers: Contracts expiring in next 90 days
    ninety_days_from_now = today + timedelta(days=90)
    renewing_customers = opportunities.filter(
        category='Customer',
        contract_expiry_date__isnull=False,
        contract_expiry_date__gte=today,
        contract_expiry_date__lte=ninety_days_from_now
    ).select_related('stage', 'assigned_to').order_by('contract_expiry_date')
    
    # DEAL/LEAD LIFECYCLE METRICS
    # New: First 50% of sales cycle (created_at to expected_close_date)
    # Expiring: Second 50% of sales cycle
    
    new_deals = []
    expiring_deals = []
    
    for opp in opportunities.filter(category__in=['Lead', 'Deal'], expected_close_date__isnull=False):
        if opp.expected_close_date and opp.created_at:
            created_date = opp.created_at.date() if hasattr(opp.created_at, 'date') else opp.created_at
            total_days = (opp.expected_close_date - created_date).days
            days_elapsed = (today - created_date).days
            
            if total_days > 0:
                progress = days_elapsed / total_days
                
                if progress < 0.5:
                    new_deals.append(opp)
                else:
                    expiring_deals.append(opp)
    
    new_deals_count = len(new_deals)
    expiring_deals_count = len(expiring_deals)
    
    # Upcoming activities
    if is_superuser:
        upcoming_activities = Activity.objects.filter(completed=False)
    elif tenant:
        upcoming_activities = Activity.objects.filter(tenant=tenant, completed=False)
    else:
        upcoming_activities = Activity.objects.filter(
            tenant=None, created_by=user, completed=False
        )
    upcoming_activities = upcoming_activities.select_related(
        'assigned_to'
    ).order_by('due_date')[:10]
    
    context = {
        'dashboard_type': dashboard_type,
        'is_superuser': is_superuser,
        'total_leads': total_leads,
        'total_deals': total_deals,
        'total_customers': total_customers,
        'total_opportunities': total_opportunities,
        'total_estimated_value': total_estimated_value,
        'total_actual_value': total_actual_value,
        'recent_opportunities': recent_opportunities,
        'upcoming_activities': upcoming_activities,
        'opportunities_by_stage': opportunities_by_stage,
        'opportunities_by_size': opportunities_by_size,
        # New metrics
        'total_partners': total_partners,
        'total_referrals': total_referrals,
        'total_contractors': total_contractors,
        'total_contacts': total_contacts,
        'companies_by_size': companies_by_size,
        # Customer categories
        'new_customers': new_customers,
        'top_customers_by_value': top_customers_by_value,
        'expanding_customers': expanding_customers,
        'renewing_customers': renewing_customers,
        # Deal/Lead lifecycle
        'new_deals_count': new_deals_count,
        'expiring_deals_count': expiring_deals_count,
        'new_deals': new_deals[:10],  # Show top 10
        'expiring_deals': expiring_deals[:10],  # Show top 10
        # Filter values for form
        'date_from': date_from,
        'date_to': date_to,
        'category_filter': category_filter,
        'stage_filter': stage_filter,
        'industry_filter': industry_filter,
        'source_filter': source_filter,
        'deal_size_filter': deal_size_filter,
    }
    
    # Superuser-specific metrics
    if is_superuser:
        # Top 10 by opportunity count (tenants + personal users)
        top_by_count = _get_top_entities_by_opportunities(opportunities)
        
        # Top 10 by expected value
        top_by_expected = _get_top_entities_by_value(opportunities, 'estimated_amount')
        
        # Top 10 by actual amount
        top_by_actual = _get_top_entities_by_value(opportunities, 'actual_amount')
        
        context.update({
            'top_by_count': top_by_count,
            'top_by_expected': top_by_expected,
            'top_by_actual': top_by_actual,
        })
    
    # Get filter options
    if is_superuser:
        stages = PipelineStage.objects.all().order_by('category', 'order')
    elif tenant:
        stages = PipelineStage.objects.filter(tenant=tenant).order_by('category', 'order')
    else:
        stages = PipelineStage.objects.filter(
            tenant=None, created_by=user
        ).order_by('category', 'order')
    
    context['stages'] = stages
    context['industries'] = Opportunity.INDUSTRY_CHOICES
    context['sources'] = Opportunity.SOURCE_CHOICES
    context['deal_sizes'] = Opportunity.DEAL_SIZE_CHOICES
    
    return render(request, 'crm/dashboard.html', context)


def _get_top_entities_by_opportunities(opportunities_qs):
    """
    Get top 10 entities (tenants + personal users) by opportunity count.
    Returns list of dicts with entity info and count.
    """
    from tenants.models import Tenant
    from documents.models import CustomUser
    
    # Aggregate by tenant
    tenant_stats = opportunities_qs.filter(
        tenant__isnull=False
    ).values(
        'tenant', 'tenant__name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Aggregate by personal user
    personal_stats = opportunities_qs.filter(
        tenant__isnull=True
    ).values(
        'created_by', 'created_by__username', 'created_by__first_name', 'created_by__last_name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Combine and format
    results = []
    
    for item in tenant_stats:
        results.append({
            'type': 'tenant',
            'id': item['tenant'],
            'name': item['tenant__name'],
            'count': item['count'],
        })
    
    for item in personal_stats:
        full_name = f"{item['created_by__first_name']} {item['created_by__last_name']}".strip()
        display_name = full_name if full_name else item['created_by__username']
        results.append({
            'type': 'personal',
            'id': item['created_by'],
            'name': display_name,
            'username': item['created_by__username'],
            'count': item['count'],
        })
    
    # Sort by count and return top 10
    results.sort(key=lambda x: x['count'], reverse=True)
    return results[:10]


def _get_top_entities_by_value(opportunities_qs, value_field):
    """
    Get top 10 entities (tenants + personal users) by value (estimated or actual amount).
    Returns list of dicts with entity info and total value.
    """
    from tenants.models import Tenant
    from documents.models import CustomUser
    
    # Aggregate by tenant
    tenant_stats = opportunities_qs.filter(
        tenant__isnull=False
    ).values(
        'tenant', 'tenant__name'
    ).annotate(
        total_value=Sum(value_field)
    ).order_by('-total_value')
    
    # Aggregate by personal user
    personal_stats = opportunities_qs.filter(
        tenant__isnull=True
    ).values(
        'created_by', 'created_by__username', 'created_by__first_name', 'created_by__last_name'
    ).annotate(
        total_value=Sum(value_field)
    ).order_by('-total_value')
    
    # Combine and format
    results = []
    
    for item in tenant_stats:
        if item['total_value']:  # Only include if there's a value
            results.append({
                'type': 'tenant',
                'id': item['tenant'],
                'name': item['tenant__name'],
                'total_value': item['total_value'],
            })
    
    for item in personal_stats:
        if item['total_value']:  # Only include if there's a value
            full_name = f"{item['created_by__first_name']} {item['created_by__last_name']}".strip()
            display_name = full_name if full_name else item['created_by__username']
            results.append({
                'type': 'personal',
                'id': item['created_by'],
                'name': display_name,
                'username': item['created_by__username'],
                'total_value': item['total_value'],
            })
    
    # Sort by value and return top 10
    results.sort(key=lambda x: x['total_value'], reverse=True)
    return results[:10]


@login_required
def opportunity_list(request):
    """List all opportunities with filtering"""
    tenant = request.effective_tenant
    user = request.effective_user
    
    opportunities = Opportunity.objects.get_assigned_or_all(user, tenant).select_related(
        'stage', 'assigned_to', 'contact'
    ).prefetch_related('products')
    
    # Filtering
    category_filter = request.GET.get('category')
    stage_filter = request.GET.get('stage')
    assigned_filter = request.GET.get('assigned_to')
    search = request.GET.get('search')
    
    if category_filter:
        opportunities = opportunities.filter(category=category_filter)
    
    if stage_filter:
        opportunities = opportunities.filter(stage_id=stage_filter)
    
    if assigned_filter:
        opportunities = opportunities.filter(assigned_to_id=assigned_filter)
    
    if search:
        opportunities = opportunities.filter(
            Q(title__icontains=search) |
            Q(company_name__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(opportunities, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get filter options
    stages = PipelineStage.objects.filter(tenant=tenant).order_by('category', 'order')
    
    context = {
        'page_obj': page_obj,
        'stages': stages,
        'category_filter': category_filter,
        'stage_filter': stage_filter,
        'assigned_filter': assigned_filter,
        'search': search,
    }
    
    return render(request, 'crm/opportunity_list.html', context)


@login_required
def opportunity_detail(request, pk):
    """View detailed information about an opportunity"""
    tenant = request.effective_tenant
    user = request.effective_user
    
    opportunity = get_object_or_404(
        Opportunity.objects.get_assigned_or_all(user, tenant).select_related(
            'stage', 'assigned_to', 'contact', 'partner_contact'
        ).prefetch_related('products'),
        pk=pk
    )
    
    # Get activities linked to this opportunity
    content_type = ContentType.objects.get_for_model(Opportunity)
    activities = Activity.objects.filter(
        tenant=tenant,
        content_type=content_type,
        object_id=opportunity.id
    ).order_by('-created_at')
    
    context = {
        'opportunity': opportunity,
        'activities': activities,
    }
    
    return render(request, 'crm/opportunity_detail.html', context)


@login_required
def opportunity_create(request):
    """Create a new opportunity"""
    return CRMCreateViewMixin().handle_create(
        request=request,
        form_class=OpportunityForm,
        template_name='crm/opportunity_form.html',
        success_url_name='crm:opportunity_detail',
        object_name='Opportunity'
    )


@login_required
def opportunity_update(request, pk):
    """Update an existing opportunity"""
    return CRMUpdateViewMixin().handle_update(
        request=request,
        pk=pk,
        model_class=Opportunity,
        form_class=OpportunityForm,
        template_name='crm/opportunity_form.html',
        success_url_name='crm:opportunity_detail',
        object_name='Opportunity'
    )


@login_required
def opportunity_delete(request, pk):
    """Delete an opportunity"""
    return CRMDeleteViewMixin().handle_delete(
        request=request,
        pk=pk,
        model_class=Opportunity,
        template_name='crm/opportunity_confirm_delete.html',
        success_url_name='crm:opportunity_list',
        list_url_name='crm:opportunity_list',
        object_name='Opportunity'
    )


@login_required
def product_list(request):
    """List all products"""
    tenant = request.effective_tenant
    user = request.effective_user
    
    products = Product.objects.get_assigned_or_all(user, tenant)
    
    # Filtering
    category_filter = request.GET.get('category')
    active_filter = request.GET.get('is_active')
    search = request.GET.get('search')
    
    if category_filter:
        products = products.filter(category=category_filter)
    
    if active_filter:
        products = products.filter(is_active=active_filter == 'true')
    
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(products, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'category_filter': category_filter,
        'active_filter': active_filter,
        'search': search,
    }
    
    return render(request, 'crm/product_list.html', context)


@login_required
def product_detail(request, pk):
    """View detailed information about a product"""
    tenant = request.effective_tenant
    user = request.effective_user
    
    product = get_object_or_404(
        Product.objects.get_assigned_or_all(user, tenant),
        pk=pk
    )
    
    # Get opportunities using this product
    opportunities = product.opportunities.filter(
        tenant=tenant
    ).order_by('-created_at')[:10]
    
    context = {
        'product': product,
        'opportunities': opportunities,
    }
    
    return render(request, 'crm/product_detail.html', context)


@login_required
def product_create(request):
    """Create a new product"""
    return CRMCreateViewMixin().handle_create(
        request=request,
        form_class=ProductForm,
        template_name='crm/product_form.html',
        success_url_name='crm:product_detail',
        object_name='Product'
    )


@login_required
def product_update(request, pk):
    """Update an existing product"""
    return CRMUpdateViewMixin().handle_update(
        request=request,
        pk=pk,
        model_class=Product,
        form_class=ProductForm,
        template_name='crm/product_form.html',
        success_url_name='crm:product_detail',
        object_name='Product'
    )


@login_required
def product_delete(request, pk):
    """Delete a product"""
    return CRMDeleteViewMixin().handle_delete(
        request=request,
        pk=pk,
        model_class=Product,
        template_name='crm/product_confirm_delete.html',
        success_url_name='crm:product_list',
        list_url_name='crm:product_list',
        object_name='Product'
    )


@login_required
def activity_create(request, content_type_id, object_id):
    """Create a new activity linked to an opportunity"""
    tenant = request.effective_tenant
    user = request.effective_user
    
    content_type = get_object_or_404(ContentType, pk=content_type_id)
    
    # Determine the redirect URL based on content type
    try:
        if content_type.model == 'opportunity':
            redirect_url = reverse('crm:opportunity_detail', kwargs={'pk': object_id})
        else:
            redirect_url = reverse('crm:dashboard')
    except Exception:
        redirect_url = reverse('crm:dashboard')
    
    if request.method == 'POST':
        form = ActivityForm(request.POST, request=request)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.tenant = tenant
            activity.created_by = user
            activity.content_type = content_type
            activity.object_id = object_id
            activity.save()
            
            messages.success(request, 'Activity created successfully.')
            return redirect(redirect_url)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ActivityForm(request=request)
    
    context = {
        'form': form,
        'action': 'Create',
        'redirect_url': redirect_url,
    }
    
    return render(request, 'crm/activity_form.html', context)

def mark_activity_completed(request, activity_id):
    activity = get_object_or_404(Activity, pk=activity_id)

    activity.mark_complete()

    return JsonResponse({
        "success": True,
        "activity_id": activity.id,
        "completed_at": activity.completed_at.strftime("%Y-%m-%d %H:%M")
    })


@login_required
def get_cities_by_country(request):
    """
    API endpoint to fetch cities for a given country code.
    Used for dynamic country-city filtering in opportunity form.
    """
    country_code = request.GET.get('country', '')
    
    if not country_code:
        return JsonResponse({'cities': []})
    
    try:
        # Get cities for the selected country, ordered by name
        cities = City.objects.filter(
            country__code2=country_code
        ).order_by('name').values('id', 'name')[:100]  # Limit to 100 cities
        
        return JsonResponse({
            'cities': list(cities)
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'cities': []
        }, status=400)


@login_required
def get_stages_by_category(request):
    """
    API endpoint to fetch pipeline stages for a given category.
    Used for dynamic category-stage filtering in opportunity form.
    """
    category = request.GET.get('category', '')
    
    if not category:
        return JsonResponse({'stages': []})
    
    try:
        # Get effective tenant
        tenant = getattr(request, 'effective_tenant', None)
        
        # Get stages for the selected category, ordered by stage order
        stages = PipelineStage.objects.filter(
            category=category,
            tenant=tenant
        ).order_by('order').values('id', 'name', 'category')
        
        return JsonResponse({
            'stages': list(stages)
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'stages': []
        }, status=400)