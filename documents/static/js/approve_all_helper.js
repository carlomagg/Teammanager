/**
 * Shared helper functions for "Approve All" functionality
 * Used across KYC/KYB review templates
 */

/**
 * Approve all fields for KYC/KYB
 */
function approveAllFields(contentTypeId, objectId) {
    // Use the shared showConfirmModal function from field_approval.js
    if (typeof showConfirmModal === 'function') {
        showConfirmModal(
            'Approve All Fields',
            'Are you sure you want to approve ALL fields? This will mark the entire submission as verified.',
            () => executeKYCApproveAll(contentTypeId, objectId)
        );
    } else {
        // Fallback if field_approval.js is not loaded
        if (confirm('Are you sure you want to approve ALL fields? This will mark the entire submission as verified.')) {
            executeKYCApproveAll(contentTypeId, objectId);
        }
    }
}

/**
 * Execute the approve all request for KYC/KYB
 */
function executeKYCApproveAll(contentTypeId, objectId) {
    fetch(`/kyc-field-approval/approve-all/${contentTypeId}/${objectId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (typeof showToast === 'function') {
                showToast('success', data.message || 'All fields approved successfully', 3000);
                setTimeout(() => location.reload(), 2000);
            } else {
                alert(data.message || 'All fields approved successfully');
                location.reload();
            }
        } else {
            if (typeof showToast === 'function') {
                showToast('danger', 'Error: ' + (data.error || 'Failed to approve all fields'));
            } else {
                alert('Error: ' + (data.error || 'Failed to approve all fields'));
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        if (typeof showToast === 'function') {
            showToast('danger', 'An error occurred while approving fields');
        } else {
            alert('An error occurred while approving fields');
        }
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
