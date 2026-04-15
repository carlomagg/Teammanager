// Edit Staff Profile JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Form submission spinner
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                const spinner = submitBtn.querySelector('.spinner-border');
                if (spinner) {
                    spinner.classList.remove('d-none');
                }
                const icon = submitBtn.querySelector('i');
                if (icon) {
                    icon.style.display = 'none';
                }
            }
        });
    });

    // Enhanced form validation
    const formControls = document.querySelectorAll('.form-control');
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

    function validateField(field) {
        const value = field.value.trim();
        const isRequired = field.hasAttribute('required');

        if (isRequired && !value) {
            field.classList.add('is-invalid');
            field.classList.remove('is-valid');
        } else {
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
        }
    }

    // Back button functionality
    const backBtn = document.querySelector('button[onclick="history.back()"]');
    if (backBtn) {
        backBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (confirm('Are you sure you want to go back? Any unsaved changes will be lost.')) {
                history.back();
            }
        });
    }
});