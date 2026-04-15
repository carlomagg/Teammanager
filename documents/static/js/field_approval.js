/**
 * Field-level approval/rejection functionality
 * Handles approve and reject actions for individual fields in KYC/KYB/Loan forms
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize toast container if it doesn't exist
    initializeToastContainer();
    
    // Handle approve button clicks
    document.querySelectorAll('.btn-approve').forEach(button => {
        button.addEventListener('click', function() {
            const fieldName = this.dataset.fieldName;
            const contentTypeId = this.dataset.contentTypeId;
            const objectId = this.dataset.objectId;
            const loanId = this.dataset.loanId; // For loan-specific approvals
            
            showConfirmModal(
                'Approve Field',
                'Are you sure you want to approve this field?',
                () => approveField(fieldName, contentTypeId, objectId, loanId)
            );
        });
    });
    
    // Handle reject button clicks
    document.querySelectorAll('.btn-reject').forEach(button => {
        button.addEventListener('click', function() {
            const fieldName = this.dataset.fieldName;
            const contentTypeId = this.dataset.contentTypeId;
            const objectId = this.dataset.objectId;
            const loanId = this.dataset.loanId; // For loan-specific rejections
            
            showRejectModal(fieldName, contentTypeId, objectId, loanId);
        });
    });
});

/**
 * Approve a field
 */
function approveField(fieldName, contentTypeId, objectId, loanId = null) {
    let url;
    if (loanId) {
        url = `/conference-loan/field-approval/${loanId}/${fieldName}/approve/`;
    } else {
        url = `/kyc-field-approval/approve/${contentTypeId}/${objectId}/${fieldName}/`;
    }
    
    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('success', data.message || 'Field approved successfully');
            updateFieldStatus(fieldName, 'approved');
            
            // If all fields approved, show success message
            if (data.all_approved) {
                showToast('success', 'All fields have been approved!', 3000);
                setTimeout(() => {
                    location.reload();
                }, 2000);
            }
        } else {
            showToast('danger', 'Error: ' + (data.error || 'Failed to approve field'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('danger', 'An error occurred while approving the field');
    });
}

/**
 * Show reject modal
 */
function showRejectModal(fieldName, contentTypeId, objectId, loanId = null) {
    const fieldLabel = document.querySelector(`[data-field-name="${fieldName}"]`)
        ?.closest('.field-approval-container')
        ?.querySelector('label')?.textContent || fieldName;
    
    // Create modal HTML
    const modalHTML = `
        <div class="modal fade" id="rejectModal" tabindex="-1" aria-labelledby="rejectModalLabel" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header bg-danger text-white">
                        <h5 class="modal-title" id="rejectModalLabel">
                            <i class="bi bi-x-circle-fill"></i> Reject Field
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <p class="mb-3">You are about to reject: <strong>${fieldLabel}</strong></p>
                        <div class="mb-3">
                            <label for="rejectionReason" class="form-label">Rejection Reason <span class="text-danger">*</span></label>
                            <textarea class="form-control" id="rejectionReason" rows="4" 
                                placeholder="Please provide a clear reason for rejection..." required></textarea>
                            <div class="form-text">Be specific so the user knows what to fix.</div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-danger" id="confirmRejectBtn">
                            <i class="bi bi-x-circle"></i> Reject Field
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    const existingModal = document.getElementById('rejectModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('rejectModal'));
    modal.show();
    
    // Handle confirm button
    document.getElementById('confirmRejectBtn').addEventListener('click', function() {
        const reason = document.getElementById('rejectionReason').value.trim();
        
        if (!reason) {
            showToast('warning', 'Rejection reason is required');
            return;
        }
        
        modal.hide();
        rejectField(fieldName, contentTypeId, objectId, reason, loanId);
    });
    
    // Clean up modal after it's hidden
    document.getElementById('rejectModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

/**
 * Reject a field
 */
function rejectField(fieldName, contentTypeId, objectId, reason, loanId = null) {
    let url;
    if (loanId) {
        url = `/conference-loan/field-approval/${loanId}/${fieldName}/reject/`;
    } else {
        url = `/kyc-field-approval/reject/${contentTypeId}/${objectId}/${fieldName}/`;
    }
    
    const formData = new FormData();
    formData.append('rejection_reason', reason);
    
    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
        },
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('success', data.message || 'Field rejected successfully');
            updateFieldStatus(fieldName, 'rejected', reason);
        } else {
            showToast('danger', 'Error: ' + (data.error || 'Failed to reject field'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('danger', 'An error occurred while rejecting the field');
    });
}

/**
 * Update field status in UI
 */
function updateFieldStatus(fieldName, status, rejectionReason = null) {
    const container = document.querySelector(`[data-field-name="${fieldName}"]`);
    if (!container) return;
    
    const statusBadge = container.querySelector('.field-status-badge');
    const approveBtn = container.querySelector('.btn-approve');
    const rejectBtn = container.querySelector('.btn-reject');
    
    // Update buttons based on status
    if (status === 'approved') {
        approveBtn?.classList.add('btn-success', 'active');
        approveBtn?.classList.remove('btn-outline-success');
        approveBtn?.setAttribute('disabled', 'disabled');
        
        rejectBtn?.classList.remove('btn-danger', 'active');
        rejectBtn?.classList.add('btn-outline-danger');
        rejectBtn?.removeAttribute('disabled');
    } else if (status === 'rejected') {
        // When rejected, disable both buttons until resubmitted
        rejectBtn?.classList.add('btn-danger', 'active');
        rejectBtn?.classList.remove('btn-outline-danger');
        rejectBtn?.setAttribute('disabled', 'disabled');
        
        approveBtn?.classList.remove('btn-success', 'active');
        approveBtn?.classList.add('btn-outline-success');
        approveBtn?.setAttribute('disabled', 'disabled');
    } else if (status === 'resubmitted') {
        // When resubmitted, enable both buttons for admin to review
        approveBtn?.classList.remove('btn-success', 'active');
        approveBtn?.classList.add('btn-outline-success');
        approveBtn?.removeAttribute('disabled');
        
        rejectBtn?.classList.remove('btn-danger', 'active');
        rejectBtn?.classList.add('btn-outline-danger');
        rejectBtn?.removeAttribute('disabled');
    }
    
    // Update status badge
    if (statusBadge) {
        let badgeHTML = '';
        if (status === 'approved') {
            badgeHTML = '<span class="badge bg-success"><i class="bi bi-check-circle-fill"></i> Approved</span>';
        } else if (status === 'rejected') {
            badgeHTML = '<span class="badge bg-danger"><i class="bi bi-x-circle-fill"></i> Rejected</span>';
            if (rejectionReason) {
                badgeHTML += `
                    <div class="alert alert-danger alert-sm mt-2 mb-0">
                        <strong>Rejection Reason:</strong> ${rejectionReason}
                    </div>
                `;
            }
        } else if (status === 'resubmitted') {
            badgeHTML = '<span class="badge bg-info"><i class="bi bi-arrow-repeat"></i> Resubmitted - Awaiting Review</span>';
        }
        statusBadge.innerHTML = badgeHTML;
    }
}

/**
 * Show confirmation modal
 */
function showConfirmModal(title, message, onConfirm) {
    const modalHTML = `
        <div class="modal fade" id="confirmModal" tabindex="-1" aria-labelledby="confirmModalLabel" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="confirmModalLabel">${title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        ${message}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" id="confirmBtn">Confirm</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    const existingModal = document.getElementById('confirmModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('confirmModal'));
    modal.show();
    
    // Handle confirm button
    document.getElementById('confirmBtn').addEventListener('click', function() {
        modal.hide();
        if (onConfirm) onConfirm();
    });
    
    // Clean up modal after it's hidden
    document.getElementById('confirmModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

/**
 * Initialize toast container
 */
function initializeToastContainer() {
    if (!document.getElementById('toastContainer')) {
        const toastContainer = document.createElement('div');
        toastContainer.id = 'toastContainer';
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }
}

/**
 * Show toast notification
 */
function showToast(type, message, duration = 5000) {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        initializeToastContainer();
    }
    
    const toastId = 'toast-' + Date.now();
    const iconMap = {
        'success': 'bi-check-circle-fill',
        'danger': 'bi-x-circle-fill',
        'warning': 'bi-exclamation-triangle-fill',
        'info': 'bi-info-circle-fill'
    };
    
    const icon = iconMap[type] || iconMap['info'];
    const bgClass = `bg-${type}`;
    
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi ${icon} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    document.getElementById('toastContainer').insertAdjacentHTML('beforeend', toastHTML);
    
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: duration
    });
    
    toast.show();
    
    // Remove toast element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        this.remove();
    });
}

/**
 * Get CSRF token from cookie
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
