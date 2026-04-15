from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Min, Max
from documents.models import Vacancy

def job_board(request):
    vacancies = Vacancy.objects.filter(status='active', is_shared=True)
    
    vacancies = apply_vacancy_filters(vacancies, request.GET)
    
    vacancies = apply_vacancy_search(vacancies, request.GET)
    
    vacancies = apply_vacancy_ordering(vacancies, request.GET)
    
    page_number = request.GET.get('page', 1)
    paginator = Paginator(vacancies, 10) 
    try:
        page_obj = paginator.page(page_number)
    except:
        page_obj = paginator.page(1)
    
    filter_data = get_filter_data(request.GET)
    
    context = {
        'vacancies': page_obj,
        'page_obj': page_obj,
        'filter_data': filter_data,
        'total_count': paginator.count,
    }
    
    return render(request, 'job_board/job_board.html', context)

def apply_vacancy_filters(queryset, params):
    city = params.get('city', '').strip()
    if city:
        queryset = queryset.filter(city__icontains=city)
    
    country = params.get('country', '').strip()
    if country:
        queryset = queryset.filter(country__iexact=country)
    
    work_mode = params.get('work_mode', '').strip()
    if work_mode:
        queryset = queryset.filter(work_mode=work_mode.lower())

    status = params.get('status', '').strip()
    if status:
        queryset = queryset.filter(status=status)
    
    min_salary = params.get('min_salary')
    if min_salary:
        try:
            queryset = queryset.filter(min_salary__gte=float(min_salary))
        except (ValueError, TypeError):
            pass
    
    max_salary = params.get('max_salary')
    if max_salary:
        try:
            queryset = queryset.filter(max_salary__lte=float(max_salary))
        except (ValueError, TypeError):
            pass
    
    skills = params.get('skills', '').strip()
    if skills:
        skills_list = [skill.strip().lower() for skill in skills.split(',')]
        query = Q()
        for skill in skills_list:
            query |= Q(skills__icontains=skill)
        queryset = queryset.filter(query)
    
    return queryset

def apply_vacancy_search(queryset, params):
    search_query = params.get('search', '').strip()
    if search_query:
        search_terms = search_query.split()
        query = Q()
        for term in search_terms:
            query |= (
                Q(title__icontains=term) |
                Q(description__icontains=term) |
                # Q(skills__icontains=term) |
                Q(eligibility__icontains=term)
            )
        queryset = queryset.filter(query)
    
    return queryset

def apply_vacancy_ordering(queryset, params):

    order_by = params.get('ordering', '-created_at')
    
    # Validate ordering fields
    allowed_ordering = [
        'created_at', '-created_at',
        'min_salary', '-min_salary',
        'max_salary', '-max_salary',
        'title', '-title',
        'city', '-city'
    ]
    
    if order_by in allowed_ordering:
        queryset = queryset.order_by(order_by)
    else:
        queryset = queryset.order_by('-created_at')
    
    return queryset

def get_filter_data(params):
    return {
        'city': params.get('city', ''),
        'country': params.get('country', ''),
        'work_mode': params.get('work_mode', ''),
        'status': params.get('status', ''),
        'min_salary': params.get('min_salary', ''),
        'max_salary': params.get('max_salary', ''),
        'skills': params.get('skills', ''),
        'search': params.get('search', ''),
        'ordering': params.get('ordering', '-created_at'),
    }

def job_board_filters_view(request):
    if request.method == 'GET' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        try:
            cities = Vacancy.objects.filter(
                status='active', 
                city__isnull=False
            ).exclude(city='').values_list('city', flat=True).distinct()
            
            countries = Vacancy.objects.filter(
                status='active', 
                country__isnull=False
            ).exclude(country='').values_list('country', flat=True).distinct()
            
            work_modes = Vacancy.objects.filter(
                status='active', 
                work_mode__isnull=False
            ).exclude(work_mode='').values_list('work_mode', flat=True).distinct()
            
            salary_range = Vacancy.objects.filter(status='active').aggregate(
                min_salary_min=Min('min_salary'),
                max_salary_max=Max('max_salary')
            )
            
            return JsonResponse({
                'success': True,
                'cities': list(cities),
                'countries': list(countries),
                'work_modes': list(work_modes),
                'salary_range': salary_range,
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def vacancy_detail_view(request, vacancy_id):
    vacancy = get_object_or_404(Vacancy, id=vacancy_id, status='active')
    
    skills_list = []
    if vacancy.skills:
        skills_list = [skill.strip() for skill in vacancy.skills.split(',') if skill.strip()]
    
    context = {
        'vacancy': vacancy,
        'skills_list': skills_list,
    }
    
    return render(request, 'job_board/vacancy_detail.html', context)

