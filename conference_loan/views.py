from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from .models import ConferenceLoan, LoanDocument, LoanComment, LoanRepayment
from .forms import ConferenceLoanForm, LoanDocumentForm, LoanCommentForm, LoanReviewForm


def is_tenant_admin(user):
    """Check if user is a tenant administrator"""
    return user.tenant and user.tenant.admin == user


def can_review_loans(user):
    """Check if user can review and approve/reject loans"""
    return user.is_superuser or is_tenant_admin(user)


@login_required
def loan_list(request):
    """List all loans for the current tenant"""
    tenant = request.user.tenant
    if not tenant:
        messages.error(request, "You must be part of an organization to access loans")
        return redirect('dashboard')
    
    # Check if user is tenant admin
    user_is_tenant_admin = is_tenant_admin(request.user)
    
    # Filter loans based on user role
    if request.user.is_superuser or user_is_tenant_admin:
        loans = ConferenceLoan.objects.filter(tenant=tenant)
    else:
        loans = ConferenceLoan.objects.filter(
            tenant=tenant,
            applicant=request.user
        )
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        loans = loans.filter(status=status_filter)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        loans = loans.filter(
            Q(reference_number__icontains=search_query) |
            Q(conference__title__icontains=search_query) |
            Q(reason__icontains=search_query)
        )
    
    # Statistics
    stats = {
        'total': loans.count(),
        'pending': loans.filter(status='pending').count(),
        'approved': loans.filter(status='approved').count(),
        'disbursed': loans.filter(status='disbursed').count(),
        'total_amount': loans.filter(status__in=['approved', 'disbursed', 'repaying', 'completed']).aggregate(
            total=Sum('approved_amount')
        )['total'] or 0,
    }
    
    context = {
        'loans': loans.order_by('-created_at'),
        'stats': stats,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'conference_loan/loan_list.html', context)


@login_required(login_url='/login/')
def loan_create(request):
    """Create a new loan application"""
    tenant = request.user.tenant
    if not tenant:
        messages.error(request, "You must be part of an organization to request loans")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ConferenceLoanForm(request.POST, request.FILES, user=request.user, tenant=tenant)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.tenant = tenant
            loan.applicant = request.user
            loan.status = 'draft'
            
            try:
                loan.save()
                
                # Refresh loan from database to ensure all relationships are loaded
                loan.refresh_from_db()
                
                # Handle all document uploads
                document_mapping = {
                    'cac_document': 'cac',
                    'cac_status_report': 'cac_status_report',
                    'memart_document': 'memart',
                    'board_resolution': 'board_resolution',
                    'scuml_certificate': 'scuml_certificate',
                    'proof_of_address': 'proof_of_address',
                    'conference_proposal': 'conference_proposal',
                    'budget': 'budget',
                    'business_plan': 'business_plan',
                    'other_document': 'other',
                }
                
                for file_field, doc_type in document_mapping.items():
                    doc_file = request.FILES.get(file_field)
                    if doc_file:
                        LoanDocument.objects.create(
                            loan=loan,
                            document_type=doc_type,
                            file=doc_file,
                            description=doc_type.replace('_', ' ').title(),
                            uploaded_by=request.user,
                            original_name=doc_file.name
                        )
                
                messages.success(request, f"Loan application {loan.reference_number} created successfully")
                
                return redirect('conference_loan:loan_detail', pk=loan.pk)
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                messages.error(request, f"Error creating loan: {str(e)}")
                print(f"Loan creation error: {error_details}")  # For debugging
        else:
            messages.error(request, "Please correct the errors below")
    else:
        form = ConferenceLoanForm(user=request.user, tenant=tenant)
    
    context = {
        'form': form,
        'title': 'Apply for Conference Loan',
    }
    return render(request, 'conference_loan/loan_form.html', context)


@login_required
def loan_detail(request, pk):
    """View loan application details"""
    loan = get_object_or_404(ConferenceLoan, pk=pk)
    
    # Check permissions
    if loan.tenant != request.user.tenant:
        raise PermissionDenied("You don't have permission to view this loan")
    
    if not (can_review_loans(request.user) or loan.applicant == request.user):
        raise PermissionDenied("You don't have permission to view this loan")
    
    # Check KYC eligibility
    is_eligible, kyc_message = loan.check_kyc_eligibility()
    
    # Handle comment submission
    if request.method == 'POST' and 'add_comment' in request.POST:
        comment_form = LoanCommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.loan = loan
            comment.author = request.user
            comment.save()
            messages.success(request, "Comment added successfully")
            return redirect('conference_loan:loan_detail', pk=pk)
    else:
        comment_form = LoanCommentForm()
    
    # Get comments (filter internal comments for non-staff)
    comments = loan.comments.all()
    if not (request.user.is_staff or request.user.is_superuser):
        comments = comments.filter(is_internal=False)
    
    context = {
        'loan': loan,
        'is_eligible': is_eligible,
        'kyc_message': kyc_message,
        'comment_form': comment_form,
        'comments': comments,
        'documents': loan.documents.all(),
        'repayments': loan.repayments.all(),
    }
    return render(request, 'conference_loan/loan_detail.html', context)


@login_required
def loan_edit(request, pk):
    """Edit loan application (only drafts)"""
    loan = get_object_or_404(ConferenceLoan, pk=pk)
    
    # Check permissions
    if loan.tenant != request.user.tenant or loan.applicant != request.user:
        raise PermissionDenied("You don't have permission to edit this loan")
    
    if loan.status != 'draft':
        messages.error(request, "Only draft loans can be edited")
        return redirect('conference_loan:loan_detail', pk=pk)
    
    if request.method == 'POST':
        form = ConferenceLoanForm(request.POST, request.FILES, instance=loan, user=request.user, tenant=request.user.tenant)
        if form.is_valid():
            form.save()
            
            # Refresh loan from database to ensure all relationships are loaded
            loan.refresh_from_db()
            
            # Handle all document uploads
            document_mapping = {
                'cac_document': 'cac',
                'cac_status_report': 'cac_status_report',
                'memart_document': 'memart',
                'board_resolution': 'board_resolution',
                'scuml_certificate': 'scuml_certificate',
                'proof_of_address': 'proof_of_address',
                'conference_proposal': 'conference_proposal',
                'budget': 'budget',
                'business_plan': 'business_plan',
                'other_document': 'other',
            }
            
            for file_field, doc_type in document_mapping.items():
                doc_file = request.FILES.get(file_field)
                if doc_file:
                    # Delete old document of same type if exists
                    loan.documents.filter(document_type=doc_type).delete()
                    LoanDocument.objects.create(
                        loan=loan,
                        document_type=doc_type,
                        file=doc_file,
                        description=doc_type.replace('_', ' ').title(),
                        uploaded_by=request.user,
                        original_name=doc_file.name
                    )
            
            messages.success(request, "Loan application updated successfully")
            
            return redirect('conference_loan:loan_detail', pk=pk)
    else:
        form = ConferenceLoanForm(instance=loan, user=request.user, tenant=request.user.tenant)
    
    # Get existing documents for display
    existing_documents = loan.documents.all()
    
    context = {
        'form': form,
        'loan': loan,
        'existing_documents': existing_documents,
        'title': 'Edit Loan Application',
    }
    return render(request, 'conference_loan/loan_form.html', context)


@login_required
def loan_submit(request, pk):
    """Submit loan for review"""
    loan = get_object_or_404(ConferenceLoan, pk=pk)
    
    # Check permissions
    if loan.tenant != request.user.tenant or loan.applicant != request.user:
        raise PermissionDenied("You don't have permission to submit this loan")
    
    if loan.status != 'draft':
        messages.error(request, "This loan has already been submitted")
        return redirect('conference_loan:loan_detail', pk=pk)
    
    try:
        loan.submit_for_review()
        
        # Initialize field approvals for granular review
        loan.get_or_create_field_approvals()
        
        messages.success(request, f"Loan {loan.reference_number} submitted for review")
    except ValidationError as e:
        messages.error(request, str(e))
    
    return redirect('conference_loan:loan_detail', pk=pk)


@login_required
def loan_upload_document(request, pk):
    """Upload supporting documents"""
    loan = get_object_or_404(ConferenceLoan, pk=pk)
    
    # Check permissions
    if loan.tenant != request.user.tenant:
        raise PermissionDenied("You don't have permission to upload documents")
    
    if not (can_review_loans(request.user) or loan.applicant == request.user):
        raise PermissionDenied("You don't have permission to upload documents")
    
    if request.method == 'POST':
        form = LoanDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.loan = loan
            document.uploaded_by = request.user
            document.original_name = request.FILES['file'].name
            document.save()
            messages.success(request, "Document uploaded successfully")
            return redirect('conference_loan:loan_detail', pk=pk)
    else:
        form = LoanDocumentForm()
    
    context = {
        'form': form,
        'loan': loan,
    }
    return render(request, 'conference_loan/upload_document.html', context)


@login_required
def loan_review(request, pk):
    """Review and approve/reject loan (tenant admin and superuser only)"""
    if not can_review_loans(request.user):
        raise PermissionDenied("Only tenant administrators and superusers can review loans")
    
    loan = get_object_or_404(ConferenceLoan, pk=pk)
    
    if loan.tenant != request.user.tenant:
        raise PermissionDenied("You don't have permission to review this loan")
    
    if loan.status not in ['pending', 'under_review']:
        messages.error(request, "This loan cannot be reviewed in its current status")
        return redirect('conference_loan:loan_detail', pk=pk)
    
    # Ensure field approvals exist for granular review
    loan.get_or_create_field_approvals()
    
    if request.method == 'POST':
        form = LoanReviewForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            
            if action == 'approve':
                loan.approve(
                    approved_amount=form.cleaned_data['approved_amount'],
                    interest_rate=form.cleaned_data['interest_rate'],
                    repayment_months=form.cleaned_data['repayment_period_months'],
                    reviewer=request.user
                )
                if form.cleaned_data.get('internal_notes'):
                    loan.internal_notes = form.cleaned_data['internal_notes']
                    loan.save()
                messages.success(request, f"Loan {loan.reference_number} approved")
            
            elif action == 'reject':
                loan.reject(
                    reason=form.cleaned_data['rejection_reason'],
                    reviewer=request.user
                )
                if form.cleaned_data.get('internal_notes'):
                    loan.internal_notes = form.cleaned_data['internal_notes']
                    loan.save()
                messages.success(request, f"Loan {loan.reference_number} rejected")
            
            return redirect('conference_loan:loan_detail', pk=pk)
    else:
        form = LoanReviewForm(initial={
            'approved_amount': loan.amount,
        })
    
    context = {
        'form': form,
        'loan': loan,
    }
    return render(request, 'conference_loan/loan_review.html', context)


@login_required
def loan_dashboard(request):
    """Dashboard showing loan statistics and overview"""
    tenant = request.user.tenant
    if not tenant:
        messages.error(request, "You must be part of an organization to access loans")
        return redirect('dashboard')
    
    # Check if user is tenant admin
    user_is_tenant_admin = is_tenant_admin(request.user)
    
    # Get loans based on user role
    if request.user.is_superuser or user_is_tenant_admin:
        all_loans = ConferenceLoan.objects.filter(tenant=tenant)
    else:
        all_loans = ConferenceLoan.objects.filter(tenant=tenant, applicant=request.user)
    
    # Statistics
    stats = {
        'total_applications': all_loans.count(),
        'pending': all_loans.filter(status='pending').count(),
        'approved': all_loans.filter(status='approved').count(),
        'disbursed': all_loans.filter(status='disbursed').count(),
        'rejected': all_loans.filter(status='rejected').count(),
        'total_approved_amount': all_loans.filter(
            status__in=['approved', 'disbursed', 'repaying', 'completed']
        ).aggregate(total=Sum('approved_amount'))['total'] or 0,
        'total_disbursed': all_loans.filter(
            status__in=['disbursed', 'repaying', 'completed']
        ).aggregate(total=Sum('approved_amount'))['total'] or 0,
        'total_repaid': all_loans.aggregate(total=Sum('total_repaid'))['total'] or 0,
    }
    
    # Recent loans
    recent_loans = all_loans.order_by('-created_at')[:5]
    
    # Pending reviews (for tenant admin and superuser)
    pending_reviews = None
    if can_review_loans(request.user):
        pending_reviews = all_loans.filter(status='pending').order_by('-submitted_at')[:10]
    
    context = {
        'stats': stats,
        'recent_loans': recent_loans,
        'pending_reviews': pending_reviews,
    }
    return render(request, 'conference_loan/dashboard.html', context)


@login_required
def check_kyc_status(request):
    """AJAX endpoint to check KYC status"""
    if not request.user.tenant:
        return JsonResponse({'eligible': False, 'message': 'No tenant found'})
    
    # Create a temporary loan object to check eligibility
    temp_loan = ConferenceLoan(
        tenant=request.user.tenant,
        applicant=request.user
    )
    
    is_eligible, message = temp_loan.check_kyc_eligibility()
    
    return JsonResponse({
        'eligible': is_eligible,
        'message': message
    })


@login_required
def admin_loan_dashboard(request):
    """Admin dashboard for reviewing and approving loans (tenant admin and superuser only)"""
    if not can_review_loans(request.user):
        messages.error(request, "Only tenant administrators and superusers can access the loan review dashboard")
        return redirect('conference_loan:dashboard')
    
    tenant = request.user.tenant
    if not tenant and not request.user.is_superuser:
        messages.error(request, "You must be part of an organization to access loans")
        return redirect('dashboard')
    
    # Get all loans for the tenant (or all if superuser)
    if request.user.is_superuser:
        all_loans = ConferenceLoan.objects.all()
    else:
        all_loans = ConferenceLoan.objects.filter(tenant=tenant)
    
    # Get current month for stats
    from datetime import datetime
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    # Statistics
    stats = {
        'draft': all_loans.filter(status='draft').count(),
        'pending': all_loans.filter(status='pending').count(),
        'under_review': all_loans.filter(status='under_review').count(),
        'approved': all_loans.filter(
            status='approved',
            reviewed_at__month=current_month,
            reviewed_at__year=current_year
        ).count(),
        'rejected': all_loans.filter(
            status='rejected',
            reviewed_at__month=current_month,
            reviewed_at__year=current_year
        ).count(),
        'disbursed': all_loans.filter(status='disbursed').count(),
        'total_requested': all_loans.aggregate(total=Sum('amount'))['total'] or 0,
        'total_approved': all_loans.filter(
            status__in=['approved', 'disbursed', 'repaying', 'completed']
        ).aggregate(total=Sum('approved_amount'))['total'] or 0,
        'total_disbursed': all_loans.filter(
            status__in=['disbursed', 'repaying', 'completed']
        ).aggregate(total=Sum('approved_amount'))['total'] or 0,
        'total_repaid': all_loans.aggregate(total=Sum('total_repaid'))['total'] or 0,
    }
    
    # Calculate outstanding balance
    stats['outstanding'] = stats['total_disbursed'] - stats['total_repaid']
    
    # Pending loans (need review)
    pending_loans = all_loans.filter(status='pending').order_by('-submitted_at')
    
    # Recently reviewed loans
    recent_reviewed = all_loans.filter(
        status__in=['approved', 'rejected']
    ).order_by('-reviewed_at')[:10]
    
    context = {
        'stats': stats,
        'pending_loans': pending_loans,
        'recent_reviewed': recent_reviewed,
    }
    return render(request, 'conference_loan/admin_loan_dashboard.html', context)
