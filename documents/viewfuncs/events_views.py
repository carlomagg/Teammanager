from django.db import models
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from documents.models import Event, CustomUser, EventParticipant, Booking, ExternalParticipant
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, status
from documents.serializers import EventSerializer, UserSerializer
from rest_framework.views import APIView
from django.middleware.csrf import get_token
from .send_mails import send_external_event_invite_email   # NEW – implement in send_mails.py
from django.utils import timezone


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.effective_user
        if user.tenant is None:
            return Event.objects.filter(created_by=user)
        return Event.objects.filter(
            models.Q(created_by=user) | models.Q(participants__user=user),
            tenant=user.tenant
        ).distinct()

    def perform_create(self, serializer):
        user = self.request.effective_user
        tenant = self.request.effective_tenant
        serializer.save(created_by=user, tenant=tenant)

    def update(self, request, *args, **kwargs):
        event = self.get_object()
        if event.created_by != request.effective_user:
            return Response({"detail": "You can only edit events you created."}, status=403)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        event = self.get_object()
        if event.created_by != request.effective_user:
            return Response({"detail": "You can only delete events you created."}, status=403)
        return super().destroy(request, *args, **kwargs)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.effective_tenant is None:
            return CustomUser.objects.none()
        return CustomUser.objects.filter(tenant=self.request.effective_tenant)


class EventParticipantResponseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, event_id):
        tenant   = request.effective_tenant
        user     = request.effective_user
        response = request.data.get('response')

        if response not in ['accepted', 'declined']:
            return Response({'error': 'Invalid response'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            participant = EventParticipant.objects.get(event_id=event_id, user=user, tenant=tenant)
            participant.response = response
            participant.save()
            return Response({'message': 'Response updated successfully'})
        except EventParticipant.DoesNotExist:
            return Response({'error': 'You are not a participant of this event'}, status=status.HTTP_403_FORBIDDEN)


@login_required
def calendar_view(request):
    CustomUser = get_user_model()
    if request.effective_user.tenant is not None:
        users = CustomUser.objects.filter(tenant=request.user.tenant)
    else:
        users = CustomUser.objects.none()
    context = {
        'csrf_token': get_token(request),
        'notification_bar_items': [],
        'birthday_others': [],
        'birthday_self': False,
        'users': users,
    }
    return render(request, 'users/calendar.html', context)


class BookingActionAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, booking_uuid, action):
        booking = get_object_or_404(Booking, uuid=booking_uuid)
        event   = booking.event

        if event.created_by != request.effective_user:
            return Response({"error": "Not authorized"}, status=403)

        if booking.status != 'pending':
            return Response({"error": f"Booking already {booking.status}"}, status=400)

        if action == 'confirm':
            booking.status = 'confirmed'
            event.status   = 'confirmed'
        elif action == 'decline':
            booking.status = 'declined'
        else:
            return Response({"error": "Invalid action"}, status=400)

        booking.save()
        event.save()

        return Response({
            "success": True,
            "booking_status": booking.status,
            "event_status": event.status,
        })


# ── NEW: invite external participants ─────────────────────────────────────────
class InviteExternalParticipantAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
 
    def post(self, request, event_id):
        event = get_object_or_404(Event, id=event_id)
        user = request.effective_user   # ← make sure this is really what you want
 
        # Authorization check
        if event.created_by != user and not (
            event.booking_type and user in event.booking_type.managers.all()
        ):
            return Response({"error": "Not authorized"}, status=403)
 
        emails = request.data.get('emails', [])
        personal_message = request.data.get('message', '').strip()
 
        if not emails:
            return Response({"error": "No emails provided"}, status=400)
 
        sent = []
        failed = []
 
        for raw_email in emails:
            email = raw_email.strip().lower()
            if not email or '@' not in email:
                failed.append({'email': raw_email, 'error': 'Invalid email'})
                continue
 
            try:
                # 1. Save/update the DB record FIRST so it's never lost even if
                #    the email delivery fails later.
                participant, created = ExternalParticipant.objects.get_or_create(
                    event=event,
                    email=email,
                    defaults={'invited_by': user},
                )
                # Always refresh invited_at on every (re-)invite.
                if not created:
                    participant.invited_at = timezone.now()
                    participant.invited_by = user
                    participant.save(update_fields=['invited_at', 'invited_by'])
 
                # 2. Now attempt to send the email (failure here is logged but
                #    the participant record is already persisted above).
                send_external_event_invite_email(
                    event=event,
                    recipient_email=email,
                    inviter=user,
                    personal_message=personal_message,
                )
 
                sent.append(email)
 
            except Exception as exc:
                failed.append({'email': email, 'error': str(exc)})
 
        return Response({
            "success": bool(sent),
            "sent": sent,
            "failed": failed,
        })