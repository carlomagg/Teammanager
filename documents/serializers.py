from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Event, EventParticipant, Notification, UserNotification, CustomUser
import logging

logger = logging.getLogger(__name__)

CustomUser = get_user_model()

class EventParticipantSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all()  # Will be filtered by tenant in __init__
    )

    class Meta:
        model = EventParticipant
        fields = ['user', 'response']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter user queryset by tenant if context is available
        if self.context.get('request'):
            if self.context['request'].effectivetenant is None:
                self.fields['user'].queryset = CustomUser.objects.none()
            tenant = self.context['request'].effectivetenant
            self.fields['user'].queryset = CustomUser.objects.filter(tenant=tenant)

    def validate_user(self, value):
        # Ensure the selected user belongs to the same tenant as the request
        request = self.context.get('request')
        if request and value.tenant != request.tenant:
            logger.error(f"Invalid user {value.username}: tenant mismatch")
            raise serializers.ValidationError("Selected user does not belong to your tenant.")
        return value

class EventSerializer(serializers.ModelSerializer):
    participants = EventParticipantSerializer(many=True, required=False)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)  # Add created_by
    
    class Meta:
        model = Event
        fields = ['id', 'title', 'description', 'start_time', 'end_time', 'participants', 'event_link', 'created_by']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        return {
            'id': str(instance.id),
            'title': instance.title,
            'start': instance.start_time.isoformat(),
            'end': instance.end_time.isoformat(),
            'description': instance.description,
            'participants': [
                {'id': participant.user.id, 'username': participant.user.username, 'response': participant.response}
                for participant in instance.participants.all()
                # participant.user.username for participant in instance.participants.all()
            ],
            'event_link': instance.event_link,
            'created_by': instance.created_by.id,  # Return creator's ID
            'external_participants': [
                {'email': ep.email, 'response': ep.response}
                for ep in instance.external_participants.all()
            ],
            'is_booking': instance.is_booking,
            'booking_for': instance.booking_type.booking_for if instance.booking_type else None,
            'color': instance.booking_type.color if instance.booking_type else None,
        }

    def validate(self, data):
        request = self.context.get('request')
        tenant = request.effective_tenant

        if tenant is None:
            # Personal user — no participants allowed
            if data.get('participants'):
                raise serializers.ValidationError(
                    "Personal accounts cannot invite participants."
                )
        else:
            # Company user — participants must match tenant
            for p in data.get('participants', []):
                if p['user'].tenant != tenant:
                    raise serializers.ValidationError(
                        f"Participant {p['user']} does not belong to your company."
                    )

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        participants_data = validated_data.pop('participants', [])

        # Always set tenant from effective context (can be None)
        validated_data['tenant'] = request.effective_tenant
        validated_data['is_booking'] = False

        event = Event.objects.create(**validated_data)

        # Participants only for company accounts
        if request.effective_tenant is not None:
            for participant_data in participants_data:
                user = participant_data['user']
                if user.tenant != request.effective_tenant:
                    raise serializers.ValidationError(
                        f"User {user.username} does not belong to the tenant."
                    )
                EventParticipant.objects.create(
                    event=event,
                    user=user,
                    tenant=request.effective_tenant,   # consistent
                    response='pending'
                )

        # Notifications — safe for both personal & company
        from documents.notification_helpers import create_event_notification
        if request.effective_tenant is not None:
            # Notify all participants (company events)
            participant_users = [p.user for p in event.participants.all()]
            if participant_users:
                create_event_notification(event, participant_users)
        else:
            # Notify creator only (personal event)
            create_event_notification(event, [event.created_by])

        return event

    def update(self, instance, validated_data):
        request = self.context.get('request')
        # Ensure the event being updated belongs to the tenant
        if instance.tenant != request.tenant:
            logger.error(f"Unauthorized update attempt on event {instance.id} by user {request.user.username}")
            raise serializers.ValidationError("You are not authorized to update this event.")

        participants_data = validated_data.pop('participants', None)
        # Update event fields
        instance = super().update(instance, validated_data)

        if participants_data is not None:
            # Get current participants
            current_participants = {p.user_id: p for p in instance.participants.all()}
            new_participant_ids = {p['user'].id for p in participants_data}

            # Remove participants not in the new list
            for user_id, participant in list(current_participants.items()):
                if user_id not in new_participant_ids:
                    participant.delete()

            # Add or update participants
            for participant_data in participants_data:
                user = participant_data['user']
                participant_data['tenant'] = request.tenant
                if user.tenant != request.tenant:
                    logger.error(f"Invalid participant {user.username}: tenant mismatch")
                    raise serializers.ValidationError(f"User {user.username} does not belong to the tenant.")
                # Check if participant already exists
                if user.id not in current_participants:
                    EventParticipant.objects.create(event=instance, **participant_data)

        return instance
    

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username']