"""
profile_views.py — Handles view_my_profile and edit_my_profile for both
UserProfile (is_personal=True) and StaffProfile (is_personal=False).

Key model relationships used here:
  - CustomUser.is_personal → True  → UserProfile (OneToOne via user_profile)
  - CustomUser.is_personal → False → StaffProfile (OneToOne via staff_profile,
                                       scoped to tenant)

Related sub-records that belong to EITHER profile type:
  EducationHistory  → staff_profile FK  OR  user_profile FK
  WorkHistory       → staff_profile FK  OR  user_profile FK
  Achievement       → staff_profile FK  OR  user_profile FK
  IdentityDocument  → staff_profile FK  OR  user_profile FK

Related sub-records that belong to StaffProfile ONLY:
  PromotionHistory  → staff_profile FK  (no user_profile equivalent)
  StaffDocument     → staff_profile FK

Ownership pattern used throughout:
  is_personal=True  → set edu.user_profile  = profile
  is_personal=False → set edu.staff_profile = profile
"""

import logging

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required

from documents.models import (
    StaffProfile,
    UserProfile,
    EducationHistory,
    WorkHistory,
    Achievement,
    IdentityDocument,
    PromotionHistory,
    Recommendation,
)
from documents.forms import (
    StaffDocumentForm,
    StaffProfileForm,
    UserProfileForm,
    EducationHistoryForm,
    WorkHistoryForm,
    AchievementForm,
    IdentityDocumentForm,
    PromotionHistoryForm,
    RecommendationForm,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_profile(user, request):
    """
    Return (profile, is_personal) for the logged-in user.
    Raises an exception / returns None if tenant check fails for staff.
    """
    is_personal = getattr(user, "is_personal", False)

    if is_personal:
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "email": user.email or "",
                "phone_number": getattr(user, "phone_number", "") or "",
            },
        )
    else:
        # Staff must have a matching tenant on the request
        if not hasattr(request, "tenant") or not request.tenant or user.tenant != request.tenant:
            logger.error(
                f"Unauthorized access by {user.username}: tenant mismatch or missing tenant"
            )
            return None, is_personal

        profile, _ = StaffProfile.objects.get_or_create(
            user=user,
            tenant=request.tenant,
            defaults={
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "email": user.email or "",
                "phone_number": getattr(user, "phone_number", "") or "",
            },
        )

    return profile, is_personal


def _owns_sub_record(record, profile, is_personal):
    """Check that a sub-record belongs to the correct profile type."""
    if is_personal:
        return getattr(record, "user_profile_id", None) == profile.pk
    return getattr(record, "staff_profile_id", None) == profile.pk


def _assign_profile_fk(obj, profile, is_personal):
    """Set the correct profile FK on a new sub-record before saving."""
    if is_personal:
        obj.user_profile = profile
    else:
        obj.staff_profile = profile


# ---------------------------------------------------------------------------
# View: view_my_profile
# ---------------------------------------------------------------------------

@login_required
def view_my_profile(request):
    user = request.user
    profile, is_personal = _get_or_create_profile(user, request)

    if profile is None:
        return render(
            request,
            "error.html",
            {
                "message": (
                    "You must be associated with a company to view this profile. "
                    "Please contact support."
                )
            },
        )

    if request.method == "POST":
        action = request.POST.get("action", "")

        # ── Bio ──────────────────────────────────────────────────────────────
        if action == "edit_bio":
            profile.bio = request.POST.get("bio", "")
            profile.save(update_fields=["bio"])

        # ── Education ────────────────────────────────────────────────────────
        elif action in ("add_education", "edit_education"):
            item_id = request.POST.get("item_id") or None
            instance = get_object_or_404(EducationHistory, id=item_id) if item_id else None
            # Ownership guard for edits
            if instance and not _owns_sub_record(instance, profile, is_personal):
                return HttpResponseForbidden("Not allowed.")
            form = EducationHistoryForm(request.POST, request.FILES, instance=instance)
            if form.is_valid():
                edu = form.save(commit=False)
                if not instance:
                    _assign_profile_fk(edu, profile, is_personal)
                edu.save()

        elif action == "delete_education":
            item_id = request.POST.get("item_id")
            edu = get_object_or_404(EducationHistory, id=item_id)
            if _owns_sub_record(edu, profile, is_personal):
                edu.delete()

        # ── Work Experience ──────────────────────────────────────────────────
        elif action in ("add_experience", "edit_experience"):
            item_id = request.POST.get("item_id") or None
            instance = get_object_or_404(WorkHistory, id=item_id) if item_id else None
            if instance and not _owns_sub_record(instance, profile, is_personal):
                return HttpResponseForbidden("Not allowed.")
            form = WorkHistoryForm(request.POST, instance=instance)
            if form.is_valid():
                exp = form.save(commit=False)
                if not instance:
                    _assign_profile_fk(exp, profile, is_personal)
                exp.save()

        elif action == "delete_experience":
            item_id = request.POST.get("item_id")
            exp = get_object_or_404(WorkHistory, id=item_id)
            if _owns_sub_record(exp, profile, is_personal):
                exp.delete()

        # ── Achievements ─────────────────────────────────────────────────────
        elif action in ("add_achievement", "edit_achievement"):
            item_id = request.POST.get("item_id") or None
            instance = get_object_or_404(Achievement, id=item_id) if item_id else None
            if instance and not _owns_sub_record(instance, profile, is_personal):
                return HttpResponseForbidden("Not allowed.")
            form = AchievementForm(request.POST, request.FILES, instance=instance)
            if form.is_valid():
                ach = form.save(commit=False)
                if not instance:
                    _assign_profile_fk(ach, profile, is_personal)
                ach.save()

        elif action == "delete_achievement":
            item_id = request.POST.get("item_id")
            ach = get_object_or_404(Achievement, id=item_id)
            if _owns_sub_record(ach, profile, is_personal):
                ach.delete()

        # ── Identity Documents ───────────────────────────────────────────────
        elif action in ("add_identity_document", "edit_identity_document"):
            item_id = request.POST.get("item_id") or None
            instance = get_object_or_404(IdentityDocument, id=item_id) if item_id else None
            if instance and not _owns_sub_record(instance, profile, is_personal):
                return HttpResponseForbidden("Not allowed.")
            form = IdentityDocumentForm(request.POST, request.FILES, instance=instance)
            if form.is_valid():
                doc = form.save(commit=False)
                if not instance:
                    _assign_profile_fk(doc, profile, is_personal)
                doc.save()

        elif action == "delete_identity_document":
            item_id = request.POST.get("item_id")
            doc = get_object_or_404(IdentityDocument, id=item_id)
            if _owns_sub_record(doc, profile, is_personal):
                doc.delete()

        # ── Promotion History (StaffProfile ONLY) ────────────────────────────
        elif action in ("add_promotion", "edit_promotion") and not is_personal:
            item_id = request.POST.get("item_id") or None
            instance = get_object_or_404(PromotionHistory, id=item_id) if item_id else None
            if instance and instance.staff_profile_id != profile.pk:
                return HttpResponseForbidden("Not allowed.")
            tenant = getattr(request, "tenant", None)
            form = PromotionHistoryForm(request.POST, request.FILES, instance=instance, tenant=tenant)
            if form.is_valid():
                promo = form.save(commit=False)
                if not instance:
                    promo.staff_profile = profile
                promo.save()

        elif action == "delete_promotion" and not is_personal:
            item_id = request.POST.get("item_id")
            promo = get_object_or_404(PromotionHistory, id=item_id)
            if promo.staff_profile_id == profile.pk:
                promo.delete()

        # ── Recommendations (delete by owner) ────────────────────────────────
        elif action == "delete_recommendation":
            item_id = request.POST.get("item_id")
            rec = get_object_or_404(Recommendation, id=item_id)
            # Only the subject (profile owner) or the recommender can delete
            is_subject = (
                (is_personal and rec.user_profile_id == profile.pk) or
                (not is_personal and rec.staff_profile_id == profile.pk)
            )
            is_author = rec.recommender_id == request.user.pk
            if is_subject or is_author:
                rec.delete()

        elif action == "toggle_recommendation_visibility":
            item_id = request.POST.get("item_id")
            rec = get_object_or_404(Recommendation, id=item_id)
            is_subject = (
                (is_personal and rec.user_profile_id == profile.pk) or
                (not is_personal and rec.staff_profile_id == profile.pk)
            )
            if is_subject:
                rec.is_visible = not rec.is_visible
                rec.save(update_fields=["is_visible"])

        return redirect("view_my_profile")

    # ── GET ──────────────────────────────────────────────────────────────────
    recommendations = (
        profile.recommendations.filter(is_visible=True)
        if not (request.user == profile.user)
        else profile.recommendations.all()  # owner sees all including hidden
    )

    context = {
        "profile": profile,
        "is_personal": is_personal,
        "is_user_profile": True,
        # Forms (always pass so modals render correctly)
        "education_form": EducationHistoryForm(),
        "experience_form": WorkHistoryForm(),
        "achievement_form": AchievementForm(),
        "identity_form": IdentityDocumentForm(),
        "recommendation_form": RecommendationForm(profile=profile),
        "recommendations": recommendations,
    }

    if not is_personal:
        tenant = getattr(request, "tenant", None)
        context["promotion_form"] = PromotionHistoryForm(tenant=tenant)
        context["document_form"] = StaffDocumentForm()

    return render(request, "dashboard/my_profile.html", context)


# ---------------------------------------------------------------------------
# View: give_recommendation  (write a rec for someone else's profile)
# ---------------------------------------------------------------------------

@login_required
def give_recommendation(request, profile_type, profile_id):
    """
    POST-only view: submit a recommendation for another user's profile.
    profile_type: 'staff' or 'user'
    profile_id:   PK of the target StaffProfile or UserProfile
    """
    if profile_type == "staff":
        target_profile = get_object_or_404(StaffProfile, pk=profile_id)
        is_personal = False
    else:
        target_profile = get_object_or_404(UserProfile, pk=profile_id)
        is_personal = True

    # Prevent recommending yourself
    if target_profile.user == request.user:
        return HttpResponseForbidden("You cannot recommend yourself.")

    if request.method == "POST":
        form = RecommendationForm(request.POST, profile=target_profile)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.recommender = request.user
            if is_personal:
                rec.user_profile = target_profile
            else:
                rec.staff_profile = target_profile
            rec.save()

    # Always redirect back to the profile being viewed
    return redirect(request.META.get("HTTP_REFERER", "view_my_profile"))


# ---------------------------------------------------------------------------
# View: delete_recommendation  (recommender deletes their own rec)
# ---------------------------------------------------------------------------

@login_required
def delete_recommendation(request, rec_id):
    rec = get_object_or_404(Recommendation, pk=rec_id)
    # Only the recommender or the subject (profile owner) can delete
    is_author = rec.recommender_id == request.user.pk
    subject_user = (
        rec.staff_profile.user if rec.staff_profile else
        rec.user_profile.user if rec.user_profile else None
    )
    is_subject = subject_user == request.user
    if not (is_author or is_subject):
        return HttpResponseForbidden("Not allowed.")
    if request.method == "POST":
        rec.delete()
    return redirect(request.META.get("HTTP_REFERER", "view_my_profile"))


# ---------------------------------------------------------------------------
# View: edit_my_profile
# ---------------------------------------------------------------------------

@login_required
def edit_my_profile(request):
    user = request.user
    profile, is_personal = _get_or_create_profile(user, request)

    if profile is None:
        return HttpResponseForbidden("You are not authorized for this company.")

    FormClass = UserProfileForm if is_personal else StaffProfileForm

    if request.method == "POST":
        if is_personal:
            form = FormClass(request.POST, request.FILES, instance=profile)
        else:
            form = FormClass(request.POST, request.FILES, instance=profile, user=user)

        if form.is_valid():
            form.save()
            return redirect("view_my_profile")
    else:
        if is_personal:
            form = FormClass(instance=profile)
        else:
            form = FormClass(instance=profile, user=user)

    context = {
        "profile": profile,
        "profile_form": form,
        "is_personal": is_personal,
    }
    if not is_personal:
        context["document_form"] = StaffDocumentForm()

    return render(request, "dashboard/edit_profile.html", context)