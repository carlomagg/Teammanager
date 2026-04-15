# teammanager/interviews/services/google_meet.py
import uuid, pytz, os, json
from django.utils import timezone
from google.oauth2 import service_account
from googleapiclient.discovery import build
from raadaa import settings
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from  django.contrib import messages
from documents.models import GoogleOAuthToken, CustomUser, Interview, GoogleOAuthState

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Load credentials once
# with open(settings.GOOGLE_CREDENTIALS_PATH, 'r') as f:
#     GOOGLE_CREDENTIALS = json.load(f)['web']
with open(settings.GOOGLE_CREDENTIALS_PATH, 'r') as f:
    client_config = json.load(f)

def get_auth_url(request, user):
    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=settings.GOOGLE_OAUTH_SCOPES,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI
    )
    
    state = str(uuid.uuid4())
    GoogleOAuthState.objects.create(state=state, user=user)
    # request.session['oauth_state'] = state
    # request.session['oauth_user_id'] = user.id

    request.session.save()
    print("AUTH START - session_key:", request.session.session_key)
    print("AUTH START - oauth_state (saved):", request.session.get('oauth_state'))
    
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        prompt='consent',               # ← forces refresh token
        include_granted_scopes='true',
        state=state
    )
    print("→ Going to Google:", auth_url)
    return auth_url


def google_oauth_callback(request):
    print("CALLBACK HIT:", request.build_absolute_uri())

    # print("CALLBACK - session_key:", request.session.session_key)
    # print("CALLBACK - oauth_state (session):", request.session.get('oauth_state'))
    print("CALLBACK - state (GET):", request.GET.get('state'))

    
    if request.GET.get('error'):
        print("Google error:", request.GET['error'])
        return redirect('interview_list')

    state = request.GET.get('state')
    if not state:
        print("Missing state")
        return redirect("interview_list")
    try:
        state_obj = GoogleOAuthState.objects.get(state=state)
    except GoogleOAuthState.DoesNotExist:
        print("Invalid state (not in DB)")
        return redirect("interview_list")
    if state_obj.is_expired():
        print("State expired")
        state_obj.delete()
        return redirect("interview_list")
    
    user = state_obj.user
    state_obj.delete()

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=settings.GOOGLE_OAUTH_SCOPES,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI
    )
    flow.state = state

    try:
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        print("Token received from Google!")
    except Exception as e:
        print("Token fetch failed:", e)
        return redirect('interview_list')

    creds = flow.credentials
    # user = CustomUser.objects.get(id=request.session['oauth_user_id'])


    # SAVE TOKEN
    GoogleOAuthToken.objects.update_or_create(
        user=user,
        defaults={
            'refresh_token': creds.refresh_token,
            'access_token': creds.token,
            'expires_at': creds.expiry,
            'client_id': client_config['web']['client_id'],
            'client_secret': client_config['web']['client_secret'],
            'token_uri': client_config['web']['token_uri'],
        }
    )
    print(f"TOKEN SAVED for {user.email} | Refresh: {creds.refresh_token[:20]}...")

    # # Clean session
    # for k in ['oauth_state', 'oauth_user_id']:
    #     request.session.pop(k, None)

    # # Resume interview creation
    # pending_id = request.session.pop('pending_interview_id', None)
    # if pending_id:
    #     try:
    #         interview = Interview.objects.get(id=pending_id)
    #         create_meet(interview)
    #         return redirect('interview_detail', pending_id)
    #     except Interview.DoesNotExist:
    #         pass

    # Resume interview creation
    pending_id = request.session.pop('pending_interview_id', None)

    if pending_id:
        try:
            interview = Interview.objects.get(id=pending_id)

            print("Resuming interview calendar creation for ID:", pending_id)

            try:
                create_meet(interview)
                print("Meet event successfully created!")
            except Exception as e:
                print("Meet creation failed:", e)

            return redirect('interview_detail', pending_id)

        except Interview.DoesNotExist:
            print("Pending interview no longer exists.")

    return redirect('interview_list')

def get_calendar_service(user):
    try:
        token = user.google_token
    except GoogleOAuthToken.DoesNotExist:
        raise ValueError("User must connect Google Calendar first.")

    if not token.refresh_token:
        raise ValueError("User must connect Google Calendar first.")
    if not token or not token.refresh_token:
        raise ValueError("User must connect Google Calendar first.")

    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri=token.token_uri,
        client_id=token.client_id,
        client_secret=token.client_secret,
        scopes=settings.GOOGLE_OAUTH_SCOPES
    )

    if creds.expired and not creds.revoked:
        creds.refresh(Request())
        token.access_token = creds.token
        token.expires_at = creds.expiry
        token.save(update_fields=['access_token', 'expires_at'])

    return build('calendar', 'v3', credentials=creds)

def create_meet(interview):
    import json
    print("\n=== CREATE MEET START ===")

    # Only virtual interviews require Meet links
    if not interview.google_meet:
        print("Not a google meet interview → skipping Meet creation.")
        return

    scheduler = interview.scheduled_by
    if not scheduler:
        print("No scheduler set → cannot create event.")
        return

    # Get Google Calendar service (may raise ValueError if not linked)
    service = get_calendar_service(scheduler)

    # ------------------------------
    # TIMEZONE HANDLING (FIXED)
    # ------------------------------
    if not interview.timezone:
        raise ValueError("Interview timezone is missing.")

    tz = pytz.timezone(interview.timezone)

    start_local = interview.schedule_start
    end_local = interview.schedule_end

    if not start_local or not end_local:
        raise ValueError("Start or end datetime is missing.")

    # Localize if naive
    if timezone.is_naive(start_local):
        start_local = tz.localize(start_local)

    if timezone.is_naive(end_local):
        end_local = tz.localize(end_local)

    print("START LOCAL:", start_local, "| tz:", start_local.tzinfo)
    print("END LOCAL:", end_local, "| tz:", end_local.tzinfo)

    # ------------------------------
    # BUILD ATTENDEE LIST (SAFE)
    # ------------------------------
    attendees = []

    # Interviewers
    for u in interview.interviewers.all():
        if u.email:
            attendees.append({"email": u.email})
        else:
            print(f"⚠️ Interviewer {u} has no email, skipping...")

    # Applicants
    for app in interview.applications.all():
        email = None

        if hasattr(app, "email") and app.email:
            email = app.email
        elif hasattr(app, "applicant") and getattr(app.applicant, "email", None):
            email = app.applicant.email

        if email:
            attendees.append({"email": email})
        else:
            print(f"⚠️ Applicant {app} has no email, skipping...")

    print("ATTENDEES:", attendees)

    # ------------------------------
    # BUILD EVENT (FIXED)
    # ------------------------------
    event = {
        "summary": f"Interview: {interview.vacancy.title}",
        "description": f"Automated interview schedule from {interview.tenant.name} ATS",
        "start": {
            "dateTime": start_local.isoformat(),
            "timeZone": interview.timezone,
        },
        "end": {
            "dateTime": end_local.isoformat(),
            "timeZone": interview.timezone,
        },
        "attendees": attendees,
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    print("EVENT BODY:", json.dumps(event, indent=2))

    # ------------------------------
    # SEND TO GOOGLE (FIXED)
    # ------------------------------
    try:
        created_event = service.events().insert(
            calendarId="primary",
            body=event,
            conferenceDataVersion=1,
            sendUpdates="all"
        ).execute()

        print("GOOGLE EVENT CREATED:", created_event)

    except Exception as e:
        print("❌ GOOGLE API ERROR:", e)
        raise

    # ------------------------------
    # SAVE EVENT ID + MEET LINK
    # ------------------------------
    interview.google_event_id = created_event.get("id")

    entry_points = (
        created_event.get("conferenceData", {})
        .get("entryPoints", [])
    )

    meet_link = next(
        (ep.get("uri") for ep in entry_points if ep.get("entryPointType") == "video"),
        created_event.get("hangoutsMeetLink")
    )

    interview.google_meet_link = meet_link
    interview.save(update_fields=["google_event_id", "google_meet_link"])

    print("MEET LINK:", meet_link)
    print("=== CREATE MEET END ===")


# def _service():
#     creds = None
#     # Token file for persistence
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)
#     # If no creds, run OAuth flow (one-time consent)
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file(
#                 'credentials.json', SCOPES  # Your OAuth JSON file
#             )
#             creds = flow.run_local_server(port=0)
#         # Save for next run
#         with open('token.json', 'w') as token:
#             token.write(creds.to_json())
#     return build("calendar", "v3", credentials=creds)

# def _service():
#     creds = service_account.Credentials.from_service_account_file(
#         settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
#     )
#     # delegated = creds.with_subject(settings.GOOGLE_CALENDAR_DELEGATED_USER)
#     # return build("calendar", "v3", credentials=delegated)
#     service = build("calendar", "v3", credentials=creds)
#     return service

# def create_meet(interview):
#     service = _service()
#     if not interview.is_virtual or not interview.timezone:
#         return

#     # Localize naive datetimes using the selected timezone
#     tz = pytz.timezone(interview.timezone)
#     if timezone.is_naive(interview.schedule_start):
#         start_local = tz.localize(interview.schedule_start)
#     else:
#         start_local = interview.schedule_start

#     if timezone.is_naive(interview.schedule_end):
#         end_local = tz.localize(interview.schedule_end)
#     else:
#         end_local = interview.schedule_end

#     # Convert to UTC for Google (required)
#     start_utc = start_local.astimezone(pytz.UTC)
#     end_utc = end_local.astimezone(pytz.UTC)

#     event = {
#         'summary': f"Interview: {interview.vacancy.title}",
#         'start': {
#             'dateTime': start_utc.isoformat(),
#             'timeZone': interview.timezone,   # This shows correct local time in Calendar
#         },
#         'end': {
#             'dateTime': end_utc.isoformat(),
#             'timeZone': interview.timezone,
#         },
#         'conferenceData': {
#             'createRequest': {
#                 'requestId': str(uuid.uuid4()),
#                 'conferenceSolutionKey': {'type': 'meet'},
#             }
#         },
#         'attendees': (
#             [{'email': u.email} for u in interview.interviewers.all()] +
#             [{'email': app.email} for app in interview.applications.all()]
#         ),
#     }

#     created_event = service.events().insert(
#         calendarId='primary',
#         body=event,
#         conferenceDataVersion=1,
#         sendUpdates='all'
#     ).execute()

#     print("Event Created Successfully!")

#     interview.google_event_id = created_event['id']
#     interview.google_meet_link = created_event.get('hangoutsMeetLink')
#     interview.save(update_fields=['google_event_id', 'google_meet_link'])