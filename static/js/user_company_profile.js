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
});