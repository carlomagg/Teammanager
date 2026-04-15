// Edit Profile JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Select2 for document type
    initializeSelect2();

    // Collapsible sections
    initializeCollapsibleSections();

    // Document management
    initializeDocumentManagement();

    // Form validation
    initializeFormValidation();

    // Modal functionality
    initializeModal();
});

function initializeSelect2() {
    const selectElement = document.getElementById('id_document_type');
    if (selectElement && typeof $ !== 'undefined' && $.fn.select2) {
        $(selectElement).select2({
            dropdownParent: $('#documentModal'),
            theme: 'bootstrap-5',
            width: '100%',
            placeholder: 'Select document type...'
        });
    }
}

function initializeCollapsibleSections() {
    const headers = document.querySelectorAll('.card-header[onclick]');
    headers.forEach(header => {
        header.addEventListener('click', function() {
            toggleVisibility(this);
        });
    });
}

function toggleVisibility(header) {
    const next = header.nextElementSibling;
    const caret = header.querySelector('.caret i');
    const isExpanded = next.classList.contains('show');

    if (next.classList.contains('collapse')) {
        $(next).collapse('toggle');
    } else {
        next.classList.toggle('show');
    }

    if (caret) {
        caret.parentElement.classList.toggle('rotated', !isExpanded);
    }

    header.setAttribute('aria-expanded', !isExpanded);
}

function initializeDocumentManagement() {
    // Add Document
    const saveBtn = document.getElementById('saveDocument');
    if (saveBtn) {
        saveBtn.addEventListener('click', addDocument);
    }

    // Delete Document
    document.addEventListener('click', function(e) {
        if (e.target.closest('.delete-document')) {
            deleteDocument(e);
        }
    });
}

function addDocument() {
    const form = document.getElementById('documentForm');
    if (!form) return;

    const formData = new FormData(form);
    const saveBtn = document.getElementById('saveDocument');
    const originalText = saveBtn.innerHTML;

    // Show loading state
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Saving...';

    fetch('{% url "add_staff_document" %}', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Add new document card
            addDocumentCard(data.document);
            // Close modal and reset form
            const modal = bootstrap.Modal.getInstance(document.getElementById('documentModal'));
            if (modal) modal.hide();
            form.reset();
            clearFormErrors();

            // Reinitialize Select2
            initializeSelect2();
        } else {
            // Show errors
            displayFormErrors(data.errors);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        displayFormErrors({'general': ['An error occurred. Please try again.']});
    })
    .finally(() => {
        // Reset button state
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    });
}

function addDocumentCard(document) {
    const container = document.getElementById('documentList');
    if (!container) return;

    const cardHtml = `
        <div class="col document-card" data-document-id="${document.id}">
            <div class="card h-100 position-relative">
                <div class="card-body">
                    <h5 class="card-title mb-3">${document.description || document.document_type}</h5>
                    <p class="card-text small">
                        <a href="${document.file_url}" target="_blank" class="text-primary text-decoration-underline" title="${document.file_name || document.file_url.split('/').pop()}">
                            ${document.file_name || document.file_url.split('/').pop().substring(0, 20)}...
                        </a><br>
                        <span class="text-muted">Type:</span> ${document.get_document_type_display || document.document_type}<br>
                        <span class="text-muted">Uploaded:</span> ${document.uploaded_at}
                    </p>
                    <button class="btn btn-danger btn-sm delete-document" title="Delete Document" aria-label="Delete Document">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', cardHtml);

    // Animate new card
    const newCard = container.lastElementChild;
    newCard.style.opacity = '0';
    newCard.style.transform = 'translateY(20px)';
    setTimeout(() => {
        newCard.style.transition = 'all 0.3s ease';
        newCard.style.opacity = '1';
        newCard.style.transform = 'translateY(0)';
    }, 10);
}

function deleteDocument(event) {
    event.preventDefault();
    const button = event.target.closest('.delete-document');
    const card = button.closest('.document-card');
    const documentId = card.dataset.documentId;

    if (confirm('Are you sure you want to delete this document?')) {
        // Show loading state
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        fetch(`{% url "delete_staff_document" document_id=0 %}`.replace('0', documentId), {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Animate removal
                card.style.transition = 'all 0.3s ease';
                card.style.opacity = '0';
                card.style.transform = 'translateY(-20px)';
                setTimeout(() => {
                    card.remove();
                    checkEmptyState();
                }, 300);
            } else {
                alert('Failed to delete document: ' + (data.error || 'Unknown error'));
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-trash"></i>';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while deleting the document.');
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-trash"></i>';
        });
    }
}

function checkEmptyState() {
    const container = document.getElementById('documentList');
    const emptyState = document.querySelector('.empty-state');

    if (container && container.children.length === 0) {
        if (!emptyState) {
            container.insertAdjacentHTML('afterend', '<p class="text-muted text-center mt-3 empty-state">No documents uploaded yet.</p>');
        }
    } else if (emptyState) {
        emptyState.remove();
    }
}

function initializeFormValidation() {
    const formControls = document.querySelectorAll('.form-control, .form-select');
    formControls.forEach(control => {
        control.addEventListener('blur', function() {
            validateField(this);
        });

        control.addEventListener('input', function() {
            if (this.classList.contains('is-invalid')) {
                validateField(this);
            }
        });
    });
}

function validateField(field) {
    const value = field.value.trim();
    const isRequired = field.hasAttribute('required');

    // Remove previous validation classes
    field.classList.remove('is-valid', 'is-invalid');

    if (isRequired && !value) {
        field.classList.add('is-invalid');
        return false;
    } else if (value) {
        field.classList.add('is-valid');
        return true;
    }

    return true;
}

function initializeModal() {
    const modal = document.getElementById('documentModal');
    if (modal) {
        modal.addEventListener('show.bs.modal', function() {
            clearFormErrors();
        });

        modal.addEventListener('hidden.bs.modal', function() {
            const form = document.getElementById('documentForm');
            if (form) form.reset();
            clearFormErrors();
        });
    }
}

function displayFormErrors(errors) {
    clearFormErrors();
    const errorContainer = document.getElementById('formErrors');

    if (errorContainer) {
        let errorHtml = '';
        for (const field in errors) {
            if (Array.isArray(errors[field])) {
                errorHtml += errors[field].join('<br>') + '<br>';
            } else {
                errorHtml += errors[field] + '<br>';
            }
        }
        errorContainer.innerHTML = errorHtml;
    }
}

function clearFormErrors() {
    const errorContainer = document.getElementById('formErrors');
    if (errorContainer) {
        errorContainer.innerHTML = '';
    }
}

// Form submission enhancement
document.addEventListener('submit', function(e) {
    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');

    if (submitBtn) {
        submitBtn.disabled = true;
        const originalHtml = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Saving...';

        // Re-enable after 10 seconds as fallback
        setTimeout(() => {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalHtml;
        }, 10000);
    }
});