from decimal import Decimal
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Min, Max, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from documents.models import Conference, ConferenceParticipant, GuestUser, ConferenceTag

from django.db.models import Min, Q

def conference_board(request):
    now = timezone.now()

    if request.GET.get('tab') == 'past':
        queryset = Conference.objects.filter(
            end_date__lt=now, is_posted=True
        ).order_by('-end_date')
        view_mode = 'past'
    else:
        queryset = Conference.objects.filter(
            end_date__gte=now, is_posted=True
        ).order_by('start_date')
        view_mode = 'upcoming'

    # Annotate with lowest active tier price (None if no tiers)
    queryset = queryset.annotate(
        min_tier_price=Min(
            'price_tiers__price',
            filter=Q(price_tiers__is_active=True)
        )
    )

    queryset = apply_conference_filters(queryset, request.GET)
    queryset = apply_conference_search(queryset, request.GET)
    queryset = apply_conference_ordering(queryset, request.GET)

    paginator = Paginator(queryset, 12)
    page_number = request.GET.get('page', 1)

    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    filter_data = get_filter_data(request.GET)

    context = {
        'conferences': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'filter_data': filter_data,
        'total_count': paginator.count,
        'is_paginated': page_obj.has_other_pages(),
        'view_mode': view_mode,
    }

    return render(request, 'conference/conference_board.html', context)


def get_filter_data(params):
    return {
        'city': params.get('city', '').strip(),
        'region': params.get('region', '').strip(),
        'country': params.get('country', '').strip(),
        'is_virtual': params.get('is_virtual', ''),
        'min_price': params.get('min_price', ''),
        'max_price': params.get('max_price', ''),
        'search': params.get('search', '').strip(),
        'ordering': params.get('ordering', 'start_date'),
        'tags': params.getlist('tags'),
    }


def apply_conference_filters(queryset, params):
    if city := params.get('city', '').strip():
        queryset = queryset.filter(venue__icontains=city)

    if region := params.get('region', '').strip():
        queryset = queryset.filter(venue__icontains=region)

    if country := params.get('country', '').strip():
        queryset = queryset.filter(venue__icontains=country)  # Fixed typo!

    if (virtual := params.get('is_virtual', '').strip()) in ('true', '1', 'True'):
        queryset = queryset.filter(is_virtual=True)
    elif virtual in ('false', '0', 'False'):
        queryset = queryset.filter(is_virtual=False)

    if min_price := params.get('min_price'):
        try:
            queryset = queryset.filter(ticket_price__gte=float(min_price))
        except (ValueError, TypeError):
            pass

    if max_price := params.get('max_price'):
        try:
            queryset = queryset.filter(ticket_price__lte=float(max_price))
        except (ValueError, TypeError):
            pass

    tags = params.get('tags', [])
    if tags:
        queryset = queryset.filter(tags__name__in=tags).distinct()

    return queryset


def apply_conference_search(queryset, params):
    search_query = params.get('search', '').strip()
    if not search_query:
        return queryset

    terms = search_query.split()
    query = Q()
    for term in terms:
        query |= (
            Q(title__icontains=term) |
            Q(description__icontains=term) |
            Q(venue__icontains=term) |
            Q(tenant__name__icontains=term) |
            Q(tags__name__icontains=term)
        )
    return queryset.filter(query)


def apply_conference_ordering(queryset, params):
    order_by = params.get('ordering', 'start_date')

    non_price_ordering = {
        'start_date': 'start_date',
        '-start_date': '-start_date',
        'title': 'title',
        '-title': '-title',
        'created': '-created_at',
    }

    if order_by in non_price_ordering:
        return queryset.order_by(non_price_ordering[order_by])

    # Price ordering: use the lowest active tier price, falling back to ticket_price
    if order_by in ('price_asc', 'price_desc'):
        queryset = queryset.annotate(
            effective_price=Coalesce(
                'min_tier_price',        # set by the board view annotation
                'ticket_price',          # fallback for tier-less conferences
                Value(Decimal('0.00')),  # final fallback if both are null
            )
        )
        direction = '' if order_by == 'price_asc' else '-'
        return queryset.order_by(f'{direction}effective_price')

    return queryset.order_by('start_date')


@require_http_methods(["GET"])
def conference_board_filters_view(request):
    """AJAX endpoint to populate dynamic filters (cities, price range, etc.)"""
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    now = timezone.now()
    base_qs = Conference.objects.filter(
        end_date__gte=now,
        venue__isnull=False
    ).exclude(venue='')

    # Extract unique venues and attempt to split city/region/country
    venues = base_qs.values_list('venue', flat=True).distinct()[:100]  # limit

    # Simple heuristic: split by comma
    cities = set()
    regions = set()
    countries = set()

    for venue in venues:
        parts = [p.strip() for p in venue.split(',')]
        if len(parts) >= 1:
            cities.add(parts[-1] if len(parts) == 1 else parts[0])
        if len(parts) >= 2:
            regions.add(parts[-2])
        if len(parts) >= 3:
            countries.add(parts[-1])

    # Price range
    price_agg = Conference.objects.filter(
        end_date__gte=now
    ).aggregate(
        min_price=Min('ticket_price'),
        max_price=Max('ticket_price')
    )

    tags = ConferenceTag.objects.filter(
        conferences__end_date__gte=now
    ).distinct().values_list('name', flat=True)[:50]

    return JsonResponse({
        'success': True,
        'cities': sorted(list(cities))[:50],
        'regions': sorted(list(regions))[:50],
        'countries': sorted(list(countries))[:50],
        'tags': sorted(list(tags)),
        'price_range': {
            'min': float(price_agg['min_price'] or 0),
            'max': float(price_agg['max_price'] or 1000),
        },
        'virtual_options': [
            {'value': 'true', 'label': 'Virtual Only'},
            {'value': 'false', 'label': 'In-Person Only'},
        ]
    })

# In your conference_post view
from django.utils import timezone
from datetime import timedelta

def conference_post(request, conference_id):
    """
    Conference post page view.

    Parameters:
    request (HttpRequest): The current request.
    conference_id (int): The ID of the conference to display.

    Returns:
    HttpResponse: A rendered HTML response for the conference post page.

    Fetches the conference with the given ID and renders the conference post page.
    Determines the current participant's status (guest or logged in) and checks if the user has already registered for the conference.
    If the user has already registered, it checks if the registration is pending (i.e. the user has not paid for the ticket yet).
    Counts the number of reserved spots for the conference (paid + pending within last 2 hours).
    """
    conference = get_object_or_404(Conference, id=conference_id, is_posted=True)
    now = timezone.now()
    if conference.end_date and conference.end_date < now:
        view_mode = 'past'
    else:
        view_mode = 'upcoming'
    
    # Determine current participant's status (guest or logged in)
    current_participant = None
    pending_participant = None
    email = None

    if request.user.is_authenticated:
        email = request.user.email
    else:
        guest_token = request.COOKIES.get('guest_token')
        if guest_token is not None and request.user.is_anonymous:
            try:
                guest = GuestUser.objects.get(token=guest_token)
                email = guest.email
            except GuestUser.DoesNotExist:
                pass

    if email:
        current_participant = ConferenceParticipant.objects.filter(
            conference=conference,
            email__iexact=email
        ).first()

        if current_participant and not current_participant.ticket_paid:
            pending_participant = current_participant

    # Reserved spots: paid + pending within last 2 hours
    recent_cutoff = timezone.now() - timedelta(hours=2)
    reserved_spots = ConferenceParticipant.objects.filter(
        conference=conference
    ).filter(
        Q(ticket_paid=True) | Q(registered_at__gte=recent_cutoff)
    ).count()

    return render(request, "conference/conference_post.html", {
        "conference": conference,
        "current_participant": current_participant,
        "pending_participant": pending_participant,
        "is_registered": current_participant is not None,
        "reserved_spots": reserved_spots,
        "view_mode": view_mode,
    })