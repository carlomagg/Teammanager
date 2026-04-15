from collections import Counter
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseForbidden
from .conference_participant_views import _generate_qr_data_uri
from documents.models import Conference, ConferenceParticipant, GuestUser, CustomUser, ConferenceTag, Feedback, CustomQuestion, ConferenceSpeaker, CustomAnswer, Folder, ConferencePriceTier
from documents.forms import ConferenceForm, ConferenceParticipantForm, ConferenceSpeakerForm, ConferencePriceTierFormSet
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.core.paginator import Paginator
from django.utils import timezone
from tenants.models import Tenant
from .helper_funcs.staff_tenant_or_user import get_tenant_or_staff
from .helper_funcs.permissions import can_create_conferences, can_edit_conferences, can_manage_conference_participant
from .helper_funcs.access_urls import build_conference_feedback_url
from raadaa import settings
from raadaa.tasks import send_conference_update_notifications
import logging, json

logger = logging.getLogger(__name__)


def conference_list(request):
    # Personal users see only their own conferences
    # Company users / staff see tenant conferences
    # Superusers/staff can see everything (possibly via ?tenant_id=)

    base_qs = Conference.objects.all()

    if request.user.is_superuser or (request.user.is_staff and not getattr(request.user, 'tenant', None)):
        # Global staff / superuser — allow override via query param or show all
        tenant = get_tenant_or_staff(request)  # your existing helper
        if tenant:
            base_qs = base_qs.filter(tenant=tenant)
    elif getattr(request.user, 'is_personal', False) or request.user.tenant is None:
        # Personal user → only their own
        base_qs = base_qs.filter(tenant__isnull=True, organizer=request.user)
    else:
        # Normal company user → only their tenant
        if not request.tenant:
            return HttpResponseForbidden("No company context.")
        base_qs = base_qs.filter(tenant=request.tenant)

    conferences = base_qs.annotate(
        participants_count=Count('participants')
    ).order_by('-start_date')

    search = request.GET.get("search")
    if search:
        conferences = conferences.filter(
            Q(title__icontains=search) |
            Q(venue__icontains=search) |
            Q(description__icontains=search) |
            Q(conference_type__icontains=search) |
            Q(tags__name__icontains=search)
        )

    paginator = Paginator(conferences, 10)  # 10 vacancies per page
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)
    return render(request, "conference/conference_list.html", {
        'conferences': page_obj,
        'can_create': can_create_conferences(request),
    })


def conference_detail(request, conference_id):
    # if not hasattr(request, 'tenant') or not request.tenant:
    #     print(f"No tenant associated with request")
    #     return HttpResponseForbidden("You are not authorized for this company.")

    tenant = get_tenant_or_staff(request)

    conference = get_object_or_404(Conference, id=conference_id, tenant=tenant)
    participants = ConferenceParticipant.objects.filter(conference=conference).order_by('-registered_at')
    participants_count = ConferenceParticipant.objects.filter(conference=conference).count()
    return render(request, "conference/conference_detail.html", {
        'conference': conference,
        'participants': participants,
        'participants_count': participants_count,
        'can_edit': can_edit_conferences(request, conference),
        'can_create': can_create_conferences(request),
    })


@login_required
def conference_create(request):
    """
    Create a new conference.
    
    Behavior:
    - Personal users (main domain, tenant=None) → can create personal conferences
    - Company admins → can create conferences for their company
    - Global staff & superusers → can create in the current effective_tenant context
    - Normal company users (non-admins) → denied
    """
    effective_user = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))

    # Permission check using the agreed helper
    if not can_create_conferences(request):
        messages.error(request, "You do not have permission to create conferences in this context.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to create conferences in this context.'
        })

    initial_custom_questions = []

    if request.method == "POST":
        form = ConferenceForm(request.POST, request.FILES, user=effective_user, tenant=effective_tenant)
        if form.is_valid():
            conference = form.save(commit=False)
            
            # Set ownership & context
            conference.tenant = effective_tenant          # None = personal conference
            conference.organizer = effective_user         # effective user (supports impersonation)

            conference.save()
            conference.tags.set(form.cleaned_data.get('tags', []))

            # ── Save price tiers ─────────────────────────────────────────────────────
            tier_formset = ConferencePriceTierFormSet(request.POST, instance=conference, prefix='tiers')
            if tier_formset.is_valid():
                tier_formset.save()
            else:
                # Non-fatal: log and warn (tiers are optional)
                logger.warning("Tier formset errors: %s", tier_formset.errors)
                messages.warning(request, "Some tier entries were invalid and skipped.")

            # ══════════════════════════════════════════════════════════
            # HANDLE UPLOAD FOLDER CREATION
            # ══════════════════════════════════════════════════════════
            create_new_folder = form.cleaned_data.get('create_new_folder', False)
            custom_folder_name = form.cleaned_data.get('custom_folder_name', '').strip()
            
            if create_new_folder:
                try:
                    # Determine folder name
                    if custom_folder_name:
                        folder_name = custom_folder_name
                    else:
                        folder_name = f"Uploads - {conference.title}"
                    
                    # Create the folder following your existing pattern
                    upload_folder = Folder.objects.create(
                        name=folder_name,
                        description=f"Participant uploads for {conference.title}",
                        created_by=effective_user,
                        tenant=effective_tenant,
                        is_public=True if effective_tenant is not None else False,  # Public for tenant, private for personal
                        parent=None  # Top-level folder
                    )
                    
                    # Assign to conference
                    conference.upload_folder = upload_folder
                    conference.save(update_fields=['upload_folder'])
                    
                    logger.info(f"Created upload folder '{folder_name}' (ID: {upload_folder.id}) for conference '{conference.title}' (ID: {conference.id})")
                    messages.success(request, f'Conference created successfully! Upload folder "{folder_name}" has been created for participants.')   
                except Exception as e:
                    logger.error(f"Error creating upload folder: {e}")
                    messages.warning(
                        request,
                        'Conference created, but there was an error creating the upload folder. '
                        'You can assign one manually from the edit page.'
                    )
            else:
                messages.success(request, 'Conference created successfully!')
            
            # ── Handle custom questions ──────────────────────────────────────
            custom_questions_json = request.POST.get('custom_questions', '[]')
            questions_created = 0
            try:
                custom_questions_data = json.loads(custom_questions_json)
                if isinstance(custom_questions_data, list):
                    for q_data in custom_questions_data:
                        if not isinstance(q_data, dict) or 'question' not in q_data:
                            continue
                        CustomQuestion.objects.create(
                            conference=conference,
                            question=q_data.get('question', '').strip(),
                            required=q_data.get('required', True),
                            order=custom_questions_data.index(q_data)  # preserve order
                        )
                        questions_created += 1
            except json.JSONDecodeError:
                messages.warning(request, "Custom questions data was invalid and skipped.")
            except Exception as e:
                messages.error(request, f"Error saving custom questions: {str(e)}")

            # ── Handle conference speakers ──────────────────────────────────────
            speaker_ids_str = request.POST.get('speaker_ids', '')
            speakers_added = 0
            
            if speaker_ids_str:
                try:
                    # Parse comma-separated speaker IDs
                    speaker_ids = [int(id.strip()) for id in speaker_ids_str.split(',')  if id.strip()]
                    
                    if speaker_ids:
                        # Get speakers for current tenant
                        speakers = ConferenceSpeaker.objects.filter(id__in=speaker_ids, tenant=effective_tenant)
                        
                        if speakers.exists():
                            # Link speakers to conference
                            conference.speakers.set(speakers)
                            speakers_added = speakers.count()
                            
                            logger.info(f"Added {speakers_added} speaker(s) to conference {conference.id}")
                        else:
                            logger.warning( f"No valid speakers found for IDs: {speaker_ids}")
                            messages.warning(request, "Some speakers could not be added (not found or access denied).")
                            
                except ValueError as e:
                    logger.error(f"Invalid speaker ID format: {e}")
                    messages.warning(
                        request,
                        "Speaker IDs were invalid and could not be processed."
                    )
                except Exception as e:
                    logger.error(f"Error adding speakers: {e}")
                    messages.warning(
                        request,
                        f"Error adding speakers: {str(e)}"
                    )

            messages.success(request, "Conference created successfully.")
            success_parts = ['Conference created successfully!']
            
            if questions_created > 0:
                success_parts.append(f'{questions_created} custom question(s) added.')
            
            if speakers_added > 0:
                success_parts.append(f'{speakers_added} speaker(s) added.')
            
            messages.success(request, ' '.join(success_parts))
            return redirect(reverse('conference_detail', kwargs={'conference_id': conference.id}))
        else:
            # Form invalid → re-populate custom questions for JS to restore
            custom_questions_json = request.POST.get('custom_questions', '[]')
            try:
                initial_custom_questions = json.loads(custom_questions_json)
            except json.JSONDecodeError:
                initial_custom_questions = []

    else:
        form = ConferenceForm(user=effective_user, tenant=effective_tenant)
        tier_formset = ConferencePriceTierFormSet(prefix='tiers')  # no instance on create GET

    return render(request, "conference/create_conference.html", {
        'form': form,
        'action': 'create',
        'is_personal_mode': effective_tenant is None,
        'current_tenant': effective_tenant,
        'can_create': can_create_conferences(request),
        'initial_custom_questions_json': json.dumps(initial_custom_questions),
        'tier_formset': tier_formset,
    })


@login_required
def conference_update(request, conference_id):
    # if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
    #     print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
    #     return HttpResponseForbidden("You are not authorized for this company.")

    effective_user   = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    conference = get_object_or_404(Conference, id=conference_id)
    old_title = conference.title
    old_theme = conference.theme
    old_description = conference.description
    old_start = conference.start_date
    old_end = conference.end_date
    old_type = conference.conference_type
    old_venue = conference.venue
    old_virtual_link = conference.virtual_link
    old_registration_deadline = conference.registration_deadline

    # Basic permission check: allow organizer or staff
    if not can_edit_conferences(request, conference):
        messages.error(request, "You do not have permission to edit this conference.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to edit this conference.'
        })
    
    # ════════════════════════════════════════════════════════════════════════
    # GET EXISTING CUSTOM QUESTIONS
    # ════════════════════════════════════════════════════════════════════════
    existing_questions = list(conference.custom_questions.all().values('id', 'question', 'required', 'order'))
    existing_questions_json = json.dumps(existing_questions)
    
    # ════════════════════════════════════════════════════════════════════════
    # GET EXISTING SPEAKERS
    # ════════════════════════════════════════════════════════════════════════
    existing_speakers = list(
        conference.speakers.all().values(
            'id', 'title', 'first_name', 'middle_name', 'last_name', 
            'designation', 'company', 'photo'
        )
    )
    existing_speakers_json = json.dumps(existing_speakers)


    if request.method == "POST":
        form = ConferenceForm(request.POST, request.FILES, instance=conference, user=effective_user, tenant=effective_tenant)
        tier_formset = ConferencePriceTierFormSet(request.POST, instance=conference, prefix='tiers')
        if form.is_valid() and tier_formset.is_valid():
            conference = form.save()  # Saves normal fields
            tags = form.cleaned_data.get('tags', [])
            conference.tags.set(tags)
            conference.updated_by = request.user
            conference.updated_at = timezone.now()
            conference.save(update_fields=['updated_by', 'updated_at'])
            # messages.success(request, "Conference updated.")

            tier_formset.save()
            
            # ══════════════════════════════════════════════════════════
            # HANDLE UPLOAD FOLDER CREATION (if creating new)
            # ══════════════════════════════════════════════════════════
            create_new_folder = form.cleaned_data.get('create_new_folder', False)
            custom_folder_name = form.cleaned_data.get('custom_folder_name', '').strip()
            
            # Only create if checkbox is checked AND conference doesn't have folder yet
            if create_new_folder and not conference.upload_folder:
                try:
                    folder_name = custom_folder_name or f"Uploads - {conference.title}"
                    
                    upload_folder = Folder.objects.create(
                        name=folder_name,
                        description=f"Participant uploads for {conference.title}",
                        created_by=effective_user,
                        tenant=effective_tenant,
                        is_public=True if effective_tenant else False,
                        parent=None
                    )
                    
                    conference.upload_folder = upload_folder
                    conference.save(update_fields=['upload_folder'])
                    
                    logger.info(f"Created upload folder '{folder_name}' for conference {conference.id}")
                except Exception as e:
                    logger.error(f"Error creating upload folder: {e}")
                    messages.warning(request, 'Error creating upload folder.')
            
            # ══════════════════════════════════════════════════════════
            # HANDLE CUSTOM QUESTIONS
            # ══════════════════════════════════════════════════════════
            custom_questions_json = request.POST.get('custom_questions', '')
            
            if custom_questions_json:
                try:
                    custom_questions_data = json.loads(custom_questions_json)
                    
                    # Delete existing questions for this conference
                    conference.custom_questions.all().delete()
                    
                    # Create new questions
                    for idx, question_data in enumerate(custom_questions_data):
                        CustomQuestion.objects.create(
                            conference=conference,
                            question=question_data['question'],
                            required=question_data.get('required', True),
                            order=idx + 1
                        )
                    
                    logger.info(f"Updated {len(custom_questions_data)} custom questions for conference {conference.id}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing custom questions JSON: {e}")
                    messages.warning(request, 'Error saving custom questions.')
                except Exception as e:
                    logger.error(f"Error saving custom questions: {e}")
                    messages.warning(request, 'Error saving custom questions.')
            else:
                # No questions submitted - delete all existing questions
                conference.custom_questions.all().delete()
            
            # ══════════════════════════════════════════════════════════
            # HANDLE SPEAKERS
            # ══════════════════════════════════════════════════════════
            speaker_ids_str = request.POST.get('speaker_ids', '')
            
            if speaker_ids_str:
                try:
                    speaker_ids = [int(sid.strip()) for sid in speaker_ids_str.split(',') if sid.strip()]
                    
                    # Get speaker objects
                    speakers = ConferenceSpeaker.objects.filter(
                        id__in=speaker_ids,
                        tenant=effective_tenant
                    )
                    
                    # Update conference speakers
                    conference.speakers.set(speakers)
                    
                    logger.info(f"Updated {len(speaker_ids)} speakers for conference {conference.id}")
                    
                except ValueError as e:
                    logger.error(f"Error parsing speaker IDs: {e}")
                    messages.warning(request, 'Error saving speakers.')
                except Exception as e:
                    logger.error(f"Error saving speakers: {e}")
                    messages.warning(request, 'Error saving speakers.')
            else:
                # No speakers submitted - clear all speakers
                conference.speakers.clear()
            
            # ══════════════════════════════════════════════════════════
            # SUCCESS MESSAGE
            # ══════════════════════════════════════════════════════════
            if create_new_folder and not conference.upload_folder:
                messages.success(
                    request,
                    f'Conference updated! Upload folder "{folder_name}" has been created.'
                )
            else:
                messages.success(request, 'Conference updated successfully!')

            send_conference_update_notifications.delay(conference.id)
            return redirect(reverse('conference_detail', kwargs={'conference_id': conference.id}))
    else:
        form = ConferenceForm(instance=conference, user=effective_user, tenant=effective_tenant)
        tier_formset = ConferencePriceTierFormSet(instance=conference, prefix='tiers')
        # Prepare existing custom questions for JavaScript
        # existing_questions = list(
        #     conference.custom_questions.all().order_by('order').values(
        #         'id', 'question', 'required', 'order'
        #     )
        # )
        
        # # Prepare existing speakers for JavaScript
        # existing_speakers = list(
        #     conference.speakers.all().values(
        #         'id', 'title', 'first_name', 'middle_name', 'last_name', 
        #         'company', 'designation', 'photo'
        #     )
        # )

    return render(request, "conference/edit_conference.html", {
        'form': form,
        'conference': conference,
        'action': 'update',
        'is_personal_mode': conference.tenant is None,
        'current_tenant': conference.tenant,
        'is_impersonating': getattr(request, 'is_impersonating', False),
        'existing_questions_json': existing_questions_json,
        'existing_speakers_json': existing_speakers_json,
        'tier_formset': tier_formset,
    })


@login_required
def conference_delete(request, conference_id):
    effective_user   = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    conference = get_object_or_404(Conference, id=conference_id, tenant=effective_tenant)

    if not can_edit_conferences(request, conference):
        messages.error(request, "You do not have permission to delete this conference.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to delete this conference.'
        })

    # # Basic permission check: allow organizer or staff
    # if not (request.user == conference.organizer or request.user.is_staff):
    #     return HttpResponseForbidden("You do not have permission to delete this conference.")

    conference.delete()
    messages.success(request, "Conference deleted.")
    next_url = request.GET.get('next')
    return redirect(next_url or 'conference_list')


# # !!!Please add functionality here
# def send_conference_confirmation():
#     pass    

def conference_tag_autocomplete(request):
    q = request.GET.get("q", "")
    tags = ConferenceTag.objects.filter(
        name__icontains=q
    ).values("id", "name")[:10]

    return JsonResponse({
        "results": [
            {"id": t["name"], "text": t["name"]} for t in tags
        ]
    })

@login_required
def post_conference(request, conference_id):
    effective_user   = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    conference = get_object_or_404(Conference, id=conference_id, tenant=effective_tenant)

    if not can_edit_conferences(request, conference):
        messages.error(request, "You do not have permission to post this conference.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to post this conference.'
        })

    now = timezone.now()

    if conference.end_date and conference.end_date < now:
        messages.error(request, "This conference has already ended — cannot post.")
        return redirect('conference_detail', conference_id=conference.id)

    if conference.is_posted:
        messages.info(request, "This conference is already posted.")
        return redirect('conference_detail', conference_id=conference.id)
    
    conference.is_posted=True
    conference.time_posted = now
    conference.save(update_fields=['is_posted', 'time_posted'])

    messages.success(request, "Conference has been posted successfully.")
    return redirect('conference_post', conference_id=conference.id)

@login_required
def withdraw_conference_post(request, conference_id):
    effective_user   = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    conference = get_object_or_404(Conference, id=conference_id, tenant=effective_tenant)

    if not can_edit_conferences(request, conference):
        messages.error(request, "You do not have permission to withdraw this conference post.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to withdraw this conference post.'
        })


    # Business rules
    if not conference.is_posted:
        messages.info(request, "This conference is not currently posted.")
        return redirect('conference_detail', conference_id=conference.id)

    # Perform action
    conference.is_posted = False
    conference.time_posted = None   # optional: clear timestamp
    conference.save(update_fields=['is_posted', 'time_posted'])

    messages.success(request, "Conference posting has been withdrawn.")
    return redirect('conference_detail', conference_id=conference.id)

@login_required
def get_conference_feedbacks(request, conference_id):
    """
    View to display all feedback for a specific conference.
    Restricted to staff members (organizers/admins).
    Shows average rating, rating distribution, and list of individual feedbacks.
    """
    conference = get_object_or_404(Conference, id=conference_id)

    # Get ContentType for Conference
    ct = ContentType.objects.get_for_model(Conference)

    # Fetch all feedback for this conference
    feedbacks_qs = Feedback.objects.filter(
        content_type=ct,
        object_id=conference.id
    ).select_related('user', 'guest_user').order_by('-created_at')

    # Pre-fetch for efficiency if you paginate later
    feedbacks = list(feedbacks_qs)

    # Calculate statistics
    ratings = [f.rating for f in feedbacks if f.rating]
    total_feedback = len(feedbacks)
    avg_rating = sum(ratings) / len(ratings) if ratings else None
    avg_rating_rounded = round(avg_rating, 2) if avg_rating else None

    # Rating distribution (1–5 stars)
    rating_counts = Counter(ratings)
    rating_distribution = {
        i: {
            'count': rating_counts.get(i, 0),
            'percentage': round((rating_counts.get(i, 0) / len(ratings) * 100), 1) if ratings else 0
        }
        for i in range(1, 6)
    }

    rating_distribution_list = []
    for i in range(5, 0, -1):
        count = rating_counts.get(i, 0)
        percentage = round((count / len(ratings) * 100), 1) if ratings else 0
        rating_distribution_list.append({
            'stars': i,
            'count': count,
            'percentage': percentage,
        })

    # Also pre-compute star display for each feedback (avoids template filter issues)
    for feedback in feedbacks:
        if feedback.rating:
            feedback.rating_display = '★' * feedback.rating + '☆' * (5 - feedback.rating)
            feedback.rating_text = f"({feedback.rating}/5)"
        else:
            feedback.rating_display = '<em>No rating</em>'
            feedback.rating_text = ''

    context = {
        'conference': conference,
        'feedbacks': feedbacks,
        'total_feedback': total_feedback,
        'avg_rating': avg_rating_rounded,
        'avg_rating_stars': '★' * round(avg_rating) + '☆' * (5 - round(avg_rating)) if avg_rating else '☆☆☆☆☆',
        'rating_distribution': rating_distribution,
        'rating_distribution_list': rating_distribution_list,
        'has_feedback': total_feedback > 0,
    }

    return render(request, 'conference/conference_feedbacks.html', context)

def conference_feedback(request, conference_id):
    """
    Unified feedback view:
    - Authenticated guests (with cookie) → auto-associate if participant match
    - Public access → allow anonymous or with provided email
    """
    conference = get_object_or_404(Conference, id=conference_id)
    now = timezone.now()

    # ───────────────────────────────────────────────
    # 1. Try to identify the submitter (priority order)
    # ───────────────────────────────────────────────
    guest_user = None
    user = request.effective_user or request.user
    participant = None
    prefilled_email = None

    if user.is_authenticated:
        participant = ConferenceParticipant.objects.filter(
            conference=conference,
            email__iexact=user.email
        ).first()

    # A. Cookie-based authenticated guest (highest priority)
    token = request.COOKIES.get('guest_token')
    if token:
        try:
            guest_user = GuestUser.objects.get(token=token)
            # Try to find matching participant
            participant = ConferenceParticipant.objects.filter(
                conference=conference,
                email__iexact=guest_user.email
            ).first()
        except GuestUser.DoesNotExist:
            guest_user = None

    # B. Public access → look for ?email= or ?participant= query param (optional)
    if not guest_user or not user.is_authenticated:
        prefilled_email = request.GET.get('email', '').strip().lower()
        if prefilled_email:
            participant = ConferenceParticipant.objects.filter(
                conference=conference,
                email__iexact=prefilled_email
            ).first()

    # C. Final participant (may still be None = truly anonymous/public)
    if not participant and prefilled_email:
        # We have an email but no participant record → still allow, but as anonymous+email
        pass

    # ───────────────────────────────────────────────
    # 2. Access / timing rules
    # ───────────────────────────────────────────────
    is_authenticated_guest = bool(guest_user)
    is_authenticated_user = user.is_authenticated

    if not is_authenticated_guest and not is_authenticated_user and not request.method == 'POST':
        # Optional: for GET, show nice message / prefill form
        if participant:
            messages.info(request, f"Detected participant: {participant.email}")
        elif prefilled_email:
            messages.info(request, "We'll associate your feedback with this email if possible.")

    # Optional strictness (you decide)
    # if conference.end_date >= now and not (participant and participant.check_in_status):
    #     if is_authenticated_guest:
    #         messages.info(request, "Feedback opens after the event ends or after check-in.")
    #         return redirect('guest_dashboard')
        # For public: either allow anyway or show message
        # messages.info(request, "This conference hasn't ended yet. Feedback may be submitted, but ...")

    # ───────────────────────────────────────────────
    # 3. Load existing feedback (respecting submitter identity)
    # ───────────────────────────────────────────────
    ct = ContentType.objects.get_for_model(Conference)

    feedback = None
    if user.is_authenticated:
        feedback = Feedback.objects.filter(
            user=user,
            content_type=ct,
            object_id=conference.id
        ).first()
    elif guest_user:
        feedback = Feedback.objects.filter(
            guest_user=guest_user,
            content_type=ct,
            object_id=conference.id
        ).first()
    elif prefilled_email:
        feedback = Feedback.objects.filter(
            anonymous_email__iexact=prefilled_email,
            content_type=ct,
            object_id=conference.id,
            user__isnull=True,
            guest_user__isnull=True
        ).first()

    # ───────────────────────────────────────────────
    # 4. Handle POST
    # ───────────────────────────────────────────────
    if request.method == 'POST':
        rating = request.POST.get('rating')
        topic = request.POST.get('topic', '').strip()
        comment = request.POST.get('comment', '').strip()
        submitted_email = request.POST.get('email', prefilled_email or '').strip().lower()
        submitted_name = request.POST.get('name', '').strip()

        if not rating and not comment:
            messages.error(request, "Please provide at least a rating or a comment.")
        else:
            defaults = {
                'tenant': conference.tenant,
                'rating': int(rating) if rating else None,
                'topic': topic or None,
                'comment': comment or None,
            }

            # Decide how to save (priority: guest > known participant email > anonymous email/name)
            if user.is_authenticated:
                obj, created = Feedback.objects.update_or_create(
                    user=user,
                    content_type=ct,
                    object_id=conference.id,
                    defaults=defaults
                )
            elif guest_user:
                obj, created = Feedback.objects.update_or_create(
                    guest_user=guest_user,
                    content_type=ct,
                    object_id=conference.id,
                    defaults=defaults
                )
            elif submitted_email:
                # Use anonymous_email (constraint will prevent duplicates)
                obj, created = Feedback.objects.update_or_create(
                    anonymous_email=submitted_email,
                    content_type=ct,
                    object_id=conference.id,
                    user__isnull=True,
                    guest_user__isnull=True,
                    defaults={**defaults, 'anonymous_name': submitted_name or None}
                )
            else:
                # Fully anonymous (no email)
                obj = Feedback.objects.create(
                    content_type=ct,
                    object_id=conference.id,
                    **defaults
                )
                created = True

            messages.success(request, "Thank you! Your feedback has been saved.")
            
            # Redirect strategy
            if is_authenticated_user:
                return redirect('user_activity_dashboard')
            elif is_authenticated_guest:
                return redirect('guest_dashboard')
            else:
                # For public users: thank-you page or back to conference page
                return redirect('conference_post', conference_id=conference.id)  # or thank-you URL

    # ───────────────────────────────────────────────
    # 5. Render
    # ───────────────────────────────────────────────
    context = {
        'conference': conference,
        'feedback': feedback,
        'participant': participant,
        'guest_user': guest_user,
        'prefilled_email': prefilled_email or (participant.email if participant else ''),
        'is_authenticated_guest': is_authenticated_guest,
        'is_authenticated_user': is_authenticated_user,
    }
    return render(request, 'conference/feedback_form.html', context)

def conference_feedback_code(request, conference_id):
    conference = get_object_or_404(Conference, id=conference_id)
    feedback_url = build_conference_feedback_url(request, conference)
    qr_data_uri = _generate_qr_data_uri(feedback_url)
    return render(request, 'conference/feedback_code.html', {'conference': conference, 'qr_data_uri': qr_data_uri, 'feedback_url': feedback_url})


@login_required
@require_http_methods(["GET"])
def get_speakers_list(request):
    """
    API endpoint to get list of speakers for the current tenant.
    Used for populating the speaker selection dropdown in the modal.
    """
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    # Get speakers for current tenant
    speakers = ConferenceSpeaker.objects.filter(tenant=effective_tenant)
    
    # Build JSON response
    speakers_data = []
    for speaker in speakers:
        speakers_data.append({
            'id': speaker.id,
            'name': str(speaker),
            'full_name': speaker.full_name_with_title,
            'designation': speaker.designation or '',
            'company': speaker.company or '',
            'photo_url': speaker.photo.url if speaker.photo else None,
        })
    
    return JsonResponse({
        'success': True,
        'speakers': speakers_data,
        'count': len(speakers_data)
    })


@login_required
@require_http_methods(["POST"])
def create_speaker_ajax(request):
    """
    AJAX endpoint to create a new speaker.
    Returns the created speaker's data as JSON.
    """
    effective_user = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    form = ConferenceSpeakerForm(request.POST, request.FILES)
    
    if form.is_valid():
        speaker = form.save(commit=False)
        speaker.tenant = effective_tenant
        speaker.created_by = effective_user
        speaker.updated_by = effective_user
        speaker.save()
        # form.save_m2m()
        
        return JsonResponse({
            'success': True,
            'message': 'Speaker created successfully',
            'speaker': {
                'id': speaker.id,
                'name': str(speaker),
                'full_name': speaker.full_name_with_title,
                'designation': speaker.designation or '',
                'company': speaker.company or '',
                'photo_url': speaker.photo.url if speaker.photo else None,
            }
        })
    else:
        # Return validation errors
        errors = {}
        for field, error_list in form.errors.items():
            errors[field] = [str(e) for e in error_list]
        
        return JsonResponse({
            'success': False,
            'message': 'Validation failed',
            'errors': errors
        }, status=400)


@login_required
@require_http_methods(["GET"])
def get_speaker_detail(request, speaker_id):
    """
    API endpoint to get details of a specific speaker.
    """
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    speaker = get_object_or_404(ConferenceSpeaker, id=speaker_id, tenant=effective_tenant)
    
    return JsonResponse({
        'success': True,
        'speaker': {
            'id': speaker.id,
            'title': speaker.title,
            'first_name': speaker.first_name,
            'middle_name': speaker.middle_name or '',
            'last_name': speaker.last_name,
            'full_name': speaker.full_name_with_title,
            'company': speaker.company or '',
            'designation': speaker.designation or '',
            'bio': speaker.bio or '',
            'email': speaker.email or '',
            'phone': speaker.phone or '',
            'linkedin_url': speaker.linkedin_url or '',
            'twitter_handle': speaker.twitter_handle or '',
            'photo_url': speaker.photo.url if speaker.photo else None,
        }
    })

@login_required
@require_http_methods(["GET"])
def get_participant_responses(request, participant_id):
    """Get custom question responses for a participant."""
    
    # Get tenant and user
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    effective_user = getattr(request, 'effective_user', request.user)
    
    # Get participant with tenant check
    participant = get_object_or_404(
        ConferenceParticipant,
        id=participant_id,
        conference__tenant=effective_tenant
    )
    
    # Permission check: only conference creator or staff
    if not (effective_user.is_staff or participant.conference.created_by == effective_user):
        return JsonResponse({
            'success': False,
            'error': 'Permission denied'
        }, status=403)
    
    # Get all responses for this participant
    responses = CustomAnswer.objects.filter(
        participant=participant
    ).select_related('custom_question').order_by('custom_question__order')
    
    # Build response data
    responses_data = []
    for response in responses:
        responses_data.append({
            'question_id': response.custom_question.id,
            'question': response.custom_question.question,
            'answer': response.answer,
            'required': response.custom_question.required,
            'order': response.custom_question.order
        })
    
    return JsonResponse({
        'success': True,
        'responses': responses_data,
        'count': len(responses_data)
    })


@login_required
def participant_detail(request, participant_id):
    """Display participant details."""
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    
    participant = get_object_or_404(
        ConferenceParticipant,
        id=participant_id,
        conference__tenant=effective_tenant
    )
    
    # Permission check
    if not can_manage_conference_participant(request, participant.conference):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'Permission denied'
        })
    
    return render(request, 'conference/participant_detail.html', {
        'participant': participant
    })
