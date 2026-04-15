from django.contrib.auth.decorators import user_passes_test
from documents.models import Team, CustomUser
from documents.forms import AssignTeamsToUsersForm, TeamForm
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render, get_object_or_404
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q

def assign_users_to_team(request, team_id):
    team = get_object_or_404(Team, id=team_id, tenant=request.tenant)
    tenant = request.tenant

    if request.method == 'POST':
        form = AssignTeamsToUsersForm(request.POST, tenant=tenant)
        if form.is_valid():
            users = form.cleaned_data['users']
            # teams = form.cleaned_data['teams']
            for user in users:
                user.teams.add(team)
            messages.success(request, f"Teams successfully assigned to users.")
            return redirect('admin_team_list')
    else:
        form = AssignTeamsToUsersForm(tenant=tenant)
    
    return render(request, 'admin/assign_users_to_team.html', {
        'form': form,
        'team': team,
    })
    
def team_members(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    members = CustomUser.objects.filter(teams=team)
    return render(request, "admin/team_members.html", {"team": team, "members": members})

@user_passes_test(is_admin)
def admin_team_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    teams = Team.objects.filter(tenant=request.tenant).order_by('department')
    search = request.GET.get("search")
    if search:
        teams = teams.filter(
            Q(name__icontains=search) |
            Q(team_leader__icontains=search) |
            Q(department__icontains=search)
        )
    paginator = Paginator(teams, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/team_list.html", {"teams": page_obj})

@user_passes_test(is_admin)
def create_team(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    if request.method == "POST":
        form = TeamForm(request.POST, user=request.user)
        if form.is_valid():
            team = form.save(commit=False)
            team.tenant = request.tenant
            team.save()
            return redirect("admin_team_list")
    else:
        form = TeamForm(user=request.user)
    return render(request, "admin/create_team.html", {"form": form})

@user_passes_test(is_admin)
def delete_team(request, team_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the team, ensuring it belongs to the same tenant
    team = get_object_or_404(Team, id=team_id, tenant=request.tenant)
    team.delete()
    next_url = request.GET.get("next")
    return redirect(next_url or "admin_team_list")

@user_passes_test(is_admin)
def edit_team(request, team_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")
    
    # Get the team, ensuring it belongs to the same tenant
    team = get_object_or_404(Team, id=team_id, tenant=request.tenant)

    if request.method == "POST":
        form = TeamForm(request.POST, instance=team, user=request.user)
        if form.is_valid():
            form.save()
            next_url = request.GET.get("next")
            return redirect(next_url or "admin_team_list")
    else:
        form = TeamForm(instance=team, user=request.user)
    return render(request, "admin/edit_team.html", {"form": form})