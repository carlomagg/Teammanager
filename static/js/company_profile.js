document.addEventListener('DOMContentLoaded', function() {
    const tabs = document.querySelectorAll('.section-tab');
    const sections = document.querySelectorAll('.profile-section');

    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const targetSection = this.getAttribute('data-section');

            // Remove active class from all tabs and sections
            tabs.forEach(t => t.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));

            // Add active class to clicked tab and corresponding section
            this.classList.add('active');
            document.getElementById(targetSection + '-section').classList.add('active');
        });
    });

    // Delete document confirmation
    document.querySelectorAll('.delete-document').forEach(btn => {
        btn.addEventListener('click', function() {
            const documentId = this.getAttribute('data-document-id');
            if (confirm('Are you sure you want to delete this document?')) {
                fetch('{% url "delete_company_document" 0 %}'.replace('0', documentId), {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': '{{ csrf_token }}',
                        'Content-Type': 'application/json'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    const card = document.querySelector(`.document-card[data-document-id="${documentId}"]`);
                    card.style.animation = 'fadeOut 0.3s ease-out forwards';
                    setTimeout(() => {
                        card.remove();
                        if (document.querySelectorAll('.document-card').length === 0) {
                            const grid = document.getElementById('documentList');
                            grid.innerHTML = '<div class="empty-state"><i class="fas fa-file-alt"></i><p>No documents uploaded</p></div>';
                        }
                    }, 300);
                })
                .catch(error => alert('Error deleting document. Please try again.'));
            }
        });
    });
});

function toggleDepartments() {
    const deptList = document.getElementById('departmentsList');
    if (deptList.style.display === 'none') {
        deptList.style.display = 'block';
    } else {
        deptList.style.display = 'none';
    }
}

function toggleTeams() {
    const teamList = document.getElementById('teamsList');
    if (teamList.style.display === 'none') {
        teamList.style.display = 'block';
    } else {
        teamList.style.display = 'none';
    }
}

function goToStaffList() {
    // window.location.href = '{% url "staff_list" %}';
    window.location.href = `/staff/list/`;
}