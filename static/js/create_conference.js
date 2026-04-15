// Toggle fields

document.addEventListener('DOMContentLoaded', function() {
    if (typeof $ !== 'undefined' && typeof $.fn.select2 !== 'undefined') {
        $('.select2').select2({ theme: 'bootstrap-5', width: '100%' });
    }
    
    // Venue fields 
    const typeRadios = document.querySelectorAll("input[name='conference_type']");
    const venueWrapper = document.getElementById("venue-wrapper");
    const virtualWrapper = document.getElementById("virtual-link-wrapper");
    const maxPhyWrapper = document.getElementById("max-phy");
    const maxVirtWrapper = document.getElementById("max-virt");

    function toggleFields() {
        const selected = document.querySelector("input[name='conference_type']:checked").value;

        if (selected === "physical") {
            venueWrapper.style.display = "block";
            virtualWrapper.style.display = "none";
            maxPhyWrapper.style.display = "block";
            maxVirtWrapper.style.display = "none";
        } else if (selected === "virtual") {
            venueWrapper.style.display = "none";
            virtualWrapper.style.display = "block";
            maxPhyWrapper.style.display = "none";
            maxVirtWrapper.style.display = "block";
        } else { // hybrid
            venueWrapper.style.display = "block";
            virtualWrapper.style.display = "block";
            maxPhyWrapper.style.display = "block";
            maxVirtWrapper.style.display = "block";
        }
    }

    typeRadios.forEach(radio => radio.addEventListener("change", toggleFields));
    toggleFields(); // initial state
    
});
$(document).ready(function () {
    $('#id_currency').select2({ width: '100%' });
    $('.select2-tags').select2({
        tags: true,
        tokenSeparators: [','],
        ajax: {
            url: "{% url 'conference_tag_autocomplete' %}",
            dataType: 'json',
            delay: 250,
            data: function (params) {
                return { q: params.term };
            },
            processResults: function (data) {
                return data;
            },
            cache: true
        },
        width: '100%'
    });

});


// Custom Questions Management
let customQuestions = [];
let questionIdCounter = 0;

document.addEventListener('DOMContentLoaded', function() {
    const enableCheckbox = document.getElementById('enableCustomQuestions');
    const questionsSection = document.getElementById('customQuestionsSection');
    const questionInput = document.getElementById('questionInput');
    const addQuestionBtn = document.getElementById('addQuestionBtn');
    const questionsList = document.getElementById('questionsList');
    const customQuestionsData = document.getElementById('customQuestionsData');

    // Toggle custom questions section
    enableCheckbox.addEventListener('change', function() {
        if (this.checked) {
            questionsSection.style.display = 'block';
            setTimeout(() => {
                questionsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);
        } else {
            questionsSection.style.display = 'none';
            // Clear questions when unchecked
            customQuestions = [];
            questionsList.innerHTML = '';
            customQuestionsData.value = '';
        }
    });

    // Add question on button click
    addQuestionBtn.addEventListener('click', function() {
        addQuestion();
    });

    // Add question on Enter key
    questionInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            addQuestion();
        }
    });

    function addQuestion() {
        const questionText = questionInput.value.trim();
        
        if (!questionText) {
            alert('Please enter a question');
            return;
        }

        if (questionText.length < 5) {
            alert('Question must be at least 5 characters long');
            return;
        }

        // Add to array
        const questionId = ++questionIdCounter;
        customQuestions.push({
            id: questionId,
            question: questionText,
            required: true
        });

        // Update hidden input
        customQuestionsData.value = JSON.stringify(customQuestions);

        // Add to display
        renderQuestion(questionId, questionText);

        // Clear input
        questionInput.value = '';
        questionInput.focus();
    }

    function renderQuestion(id, text) {
        const questionCard = document.createElement('div');
        questionCard.className = 'card mb-2';
        questionCard.id = `question-${id}`;
        questionCard.innerHTML = `
            <div class="card-body p-3">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <div class="d-flex align-items-center mb-2">
                            <span class="badge bg-primary me-2">Q${customQuestions.length}</span>
                            <strong class="text-dark">${escapeHtml(text)}</strong>
                        </div>
                        
                        <!-- Preview Response Field -->
                        <div class="mt-3 mb-2">
                            <label class="form-label small text-muted">
                                <i class="fas fa-eye me-1"></i>Preview: Participant's response field
                            </label>
                            <input type="text" 
                                    class="form-control form-control-sm bg-light" 
                                    placeholder="Participants will type their answer here..."
                                    disabled>
                            <small class="text-muted">This is how the question will appear to participants</small>
                        </div>
                        
                        <div class="form-check form-check-inline mt-2">
                            <input class="form-check-input" 
                                    type="checkbox" 
                                    id="required-${id}" 
                                    checked
                                    onchange="toggleRequired(${id}, this.checked)">
                            <label class="form-check-label small text-muted" for="required-${id}">
                                Required
                            </label>
                        </div>
                    </div>
                    <button type="button" 
                            class="btn btn-sm btn-outline-danger" 
                            onclick="removeQuestion(${id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        questionsList.appendChild(questionCard);
    }

    // Make functions globally available
    window.removeQuestion = function(id) {
        if (confirm('Remove this question?')) {
            // Remove from array
            customQuestions = customQuestions.filter(q => q.id !== id);
            
            // Update hidden input
            customQuestionsData.value = JSON.stringify(customQuestions);
            
            // Remove from display
            const element = document.getElementById(`question-${id}`);
            if (element) {
                element.remove();
            }

            // Re-render all questions to update numbering
            questionsList.innerHTML = '';
            customQuestions.forEach((q, index) => {
                const card = document.createElement('div');
                card.className = 'card mb-2';
                card.id = `question-${q.id}`;
                card.innerHTML = `
                    <div class="card-body p-3">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <div class="d-flex align-items-center mb-2">
                                    <span class="badge bg-primary me-2">Q${index + 1}</span>
                                    <strong class="text-dark">${escapeHtml(q.question)}</strong>
                                </div>
                                
                                <!-- Preview Response Field -->
                                <div class="mt-3 mb-2">
                                    <label class="form-label small text-muted">
                                        <i class="fas fa-eye me-1"></i>Preview: Participant's response field
                                    </label>
                                    <input type="text" 
                                            class="form-control form-control-sm bg-light" 
                                            placeholder="Participants will type their answer here..."
                                            disabled>
                                    <small class="text-muted">This is how the question will appear to participants</small>
                                </div>
                                
                                <div class="form-check form-check-inline mt-2">
                                    <input class="form-check-input" 
                                            type="checkbox" 
                                            id="required-${q.id}" 
                                            ${q.required ? 'checked' : ''}
                                            onchange="toggleRequired(${q.id}, this.checked)">
                                    <label class="form-check-label small text-muted" for="required-${q.id}">
                                        Required
                                    </label>
                                </div>
                            </div>
                            <button type="button" 
                                    class="btn btn-sm btn-outline-danger" 
                                    onclick="removeQuestion(${q.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `;
                questionsList.appendChild(card);
            });
        }
    };

    window.toggleRequired = function(id, required) {
        const question = customQuestions.find(q => q.id === id);
        if (question) {
            question.required = required;
            customQuestionsData.value = JSON.stringify(customQuestions);
        }
    };

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});

// Existing scripts
document.querySelectorAll('select').forEach(function(s){ 
    if (!s.closest('#speakerModal')) {
        s.classList.add('select2');
    }
});


// <!-- SPEAKER MODAL JAVASCRIPT -->

document.addEventListener('DOMContentLoaded', function() {
    // ===================================================================
    // SPEAKER MODAL FUNCTIONALITY
    // ===================================================================
    
    const speakerModal = document.getElementById('speakerModal');
    const speakersListContainer = document.getElementById('speakers-list-container');
    const selectedSpeakersList = document.getElementById('selected-speakers-list');
    const speakerIdsInput = document.getElementById('speaker_ids');
    const addSelectedBtn = document.getElementById('add-selected-speaker-btn');
    const createSpeakerBtn = document.getElementById('create-speaker-btn');
    const createSpeakerForm = document.getElementById('create-speaker-form');
    const speakerSearch = document.getElementById('speaker-search');
    
    let allSpeakers = [];
    let selectedSpeakerInModal = null;
    let selectedSpeakersData = [];
    
    // Load speakers when modal opens
    speakerModal.addEventListener('show.bs.modal', function() {
        loadSpeakers();
    });
    
    // Tab switching
    document.getElementById('select-speaker-tab').addEventListener('click', function() {
        addSelectedBtn.style.display = 'inline-block';
        createSpeakerBtn.style.display = 'none';
    });
    
    document.getElementById('create-speaker-tab').addEventListener('click', function() {
        addSelectedBtn.style.display = 'none';
        createSpeakerBtn.style.display = 'inline-block';
    });
    
    // ===================================================================
    // LOAD EXISTING SPEAKERS
    // ===================================================================
    
    function loadSpeakers() {
        fetch(`/conference/speakers/list/`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    allSpeakers = data.speakers;
                    displaySpeakers(allSpeakers);
                } else {
                    showError('Failed to load speakers');
                }
            })
            .catch(error => {
                console.error('Error loading speakers:', error);
                showError('Error loading speakers');
            });
    }
    
    function displaySpeakers(speakers) {
        if (speakers.length === 0) {
            speakersListContainer.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-users fa-3x text-muted mb-3"></i>
                    <p class="text-muted">No speakers found. Create your first speaker!</p>
                </div>
            `;
            return;
        }
        
        let html = '';
        speakers.forEach(speaker => {
            const isSelected = selectedSpeakersData.some(s => s.id === speaker.id);
            const selectedClass = isSelected ? 'selected' : '';
            
            html += `
                <div class="list-group-item speaker-list-item ${selectedClass}" 
                     data-speaker-id="${speaker.id}"
                     onclick="selectSpeaker(${speaker.id})">
                    <div class="d-flex align-items-center">
                        ${speaker.photo_url ? `
                            <img src="${speaker.photo_url}" 
                                 alt="${speaker.full_name}" 
                                 class="speaker-avatar me-3">
                        ` : `
                            <div class="speaker-avatar me-3 bg-secondary text-white d-flex align-items-center justify-content-center">
                                <i class="fas fa-user"></i>
                            </div>
                        `}
                        <div class="flex-grow-1">
                            <h6 class="mb-1">${speaker.full_name}</h6>
                            ${speaker.designation && speaker.company ? `
                                <small class="text-muted">${speaker.designation} at ${speaker.company}</small>
                            ` : speaker.designation ? `
                                <small class="text-muted">${speaker.designation}</small>
                            ` : speaker.company ? `
                                <small class="text-muted">${speaker.company}</small>
                            ` : ''}
                        </div>
                        ${isSelected ? `
                            <span class="badge bg-success">
                                <i class="fas fa-check me-1"></i>Selected
                            </span>
                        ` : ''}
                    </div>
                </div>
            `;
        });
        
        speakersListContainer.innerHTML = html;
    }
    
    // ===================================================================
    // SPEAKER SEARCH
    // ===================================================================
    
    if (speakerSearch) {
        speakerSearch.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            
            if (!searchTerm) {
                displaySpeakers(allSpeakers);
                return;
            }
            
            const filtered = allSpeakers.filter(speaker => {
                return speaker.full_name.toLowerCase().includes(searchTerm) ||
                       (speaker.company && speaker.company.toLowerCase().includes(searchTerm)) ||
                       (speaker.designation && speaker.designation.toLowerCase().includes(searchTerm));
            });
            
            displaySpeakers(filtered);
        });
    }
    
    // ===================================================================
    // SELECT SPEAKER FROM LIST
    // ===================================================================
    
    window.selectSpeaker = function(speakerId) {
        const speaker = allSpeakers.find(s => s.id === speakerId);
        if (!speaker) return;
        
        const alreadySelected = selectedSpeakersData.some(s => s.id === speakerId);
        
        if (alreadySelected) {
            selectedSpeakersData = selectedSpeakersData.filter(s => s.id !== speakerId);
            selectedSpeakerInModal = null;
        } else {
            selectedSpeakerInModal = speaker;
        }
        
        displaySpeakers(allSpeakers);
    };
    
    // Add selected speaker button
    if (addSelectedBtn) {
        addSelectedBtn.addEventListener('click', function() {
            if (!selectedSpeakerInModal) {
                alert('Please select a speaker');
                return;
            }
            
            if (!selectedSpeakersData.some(s => s.id === selectedSpeakerInModal.id)) {
                selectedSpeakersData.push(selectedSpeakerInModal);
                updateSelectedSpeakersDisplay();
                updateHiddenInput();
            }
            
            bootstrap.Modal.getInstance(speakerModal).hide();
            selectedSpeakerInModal = null;
        });
    }
    
    // ===================================================================
    // CREATE NEW SPEAKER
    // ===================================================================
    
    if (createSpeakerBtn && createSpeakerForm) {
        createSpeakerBtn.addEventListener('click', function() {
            const btn = this;
            const btnText = btn.querySelector('.btn-text');
            const spinner = btn.querySelector('.spinner-border');
            
            if (!createSpeakerForm.checkValidity()) {
                createSpeakerForm.reportValidity();
                return;
            }
            
            btn.disabled = true;
            btnText.textContent = 'Creating...';
            spinner.classList.remove('d-none');
            
            const formData = new FormData(createSpeakerForm);
            
            fetch(`/conference/speakers/create/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': formData.get('csrfmiddlewaretoken')
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    selectedSpeakersData.push(data.speaker);
                    allSpeakers.push(data.speaker);
                    
                    updateSelectedSpeakersDisplay();
                    updateHiddenInput();
                    displaySpeakers(allSpeakers);
                    
                    showSuccess('Speaker created successfully!');
                    createSpeakerForm.reset();
                    bootstrap.Modal.getInstance(speakerModal).hide();
                } else {
                    showFormErrors(data.errors || {message: data.message});
                }
            })
            .catch(error => {
                console.error('Error creating speaker:', error);
                showError('Failed to create speaker. Please try again.');
            })
            .finally(() => {
                btn.disabled = false;
                btnText.textContent = 'Create & Add Speaker';
                spinner.classList.add('d-none');
            });
        });
    }
    
    // ===================================================================
    // UPDATE SELECTED SPEAKERS DISPLAY
    // ===================================================================
    
    function updateSelectedSpeakersDisplay() {
        if (selectedSpeakersData.length === 0) {
            selectedSpeakersList.innerHTML = `
                <div class="col-12">
                    <p class="text-muted mb-0">No speakers added yet.</p>
                </div>
            `;
            return;
        }
        
        let html = '';
        selectedSpeakersData.forEach(speaker => {
            html += `
                <div class="col-md-6 col-lg-4">
                    <div class="card h-100">
                        <div class="card-body position-relative">
                            <button type="button" 
                                    class="remove-speaker-btn" 
                                    onclick="removeSpeaker(${speaker.id})"
                                    title="Remove speaker">
                                <i class="fas fa-times"></i>
                            </button>
                            
                            <div class="text-center mb-2">
                                ${speaker.photo_url ? `
                                    <img src="${speaker.photo_url}" 
                                         alt="${speaker.full_name}" 
                                         class="speaker-avatar-lg">
                                ` : `
                                    <div class="speaker-avatar-lg mx-auto bg-secondary text-white d-flex align-items-center justify-content-center">
                                        <i class="fas fa-user fa-2x"></i>
                                    </div>
                                `}
                            </div>
                            
                            <h6 class="text-center mb-1">${speaker.full_name}</h6>
                            
                            ${speaker.designation && speaker.company ? `
                                <p class="text-center text-muted small mb-0">
                                    ${speaker.designation}<br>${speaker.company}
                                </p>
                            ` : speaker.designation ? `
                                <p class="text-center text-muted small mb-0">${speaker.designation}</p>
                            ` : speaker.company ? `
                                <p class="text-center text-muted small mb-0">${speaker.company}</p>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
        
        selectedSpeakersList.innerHTML = html;
    }
    
    window.removeSpeaker = function(speakerId) {
        selectedSpeakersData = selectedSpeakersData.filter(s => s.id !== speakerId);
        updateSelectedSpeakersDisplay();
        updateHiddenInput();
        displaySpeakers(allSpeakers);
    };
    
    function updateHiddenInput() {
        const speakerIds = selectedSpeakersData.map(s => s.id);
        speakerIdsInput.value = speakerIds.join(',');
    }
    
    function showSuccess(message) {
        const messagesDiv = document.getElementById('speaker-form-messages');
        messagesDiv.innerHTML = `
            <div class="alert alert-success alert-dismissible fade show">
                <i class="fas fa-check-circle me-2"></i>${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
    }
    
    function showError(message) {
        const messagesDiv = document.getElementById('speaker-form-messages');
        messagesDiv.innerHTML = `
            <div class="alert alert-danger alert-dismissible fade show">
                <i class="fas fa-exclamation-circle me-2"></i>${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
    }
    
    function showFormErrors(errors) {
        let html = '<div class="alert alert-danger"><ul class="mb-0">';
        
        for (const [field, messages] of Object.entries(errors)) {
            messages.forEach(msg => {
                html += `<li>${field}: ${msg}</li>`;
            });
        }
        
        html += '</ul></div>';
        
        document.getElementById('speaker-form-messages').innerHTML = html;
    }
});



// Load existing custom questions
document.addEventListener('DOMContentLoaded', function() {
    const existingQuestionsJson = '{{ existing_questions_json|safe }}';
    
    if (existingQuestionsJson && existingQuestionsJson !== '[]') {
        const existingQuestions = JSON.parse(existingQuestionsJson);
        
        if (existingQuestions.length > 0) {
            // Enable section
            document.getElementById('enableCustomQuestions').checked = true;
            document.getElementById('customQuestionsSection').style.display = 'block';
            
            // Load questions
            existingQuestions.forEach(function(q) {
                questionIdCounter++;
                customQuestions.push({
                    id: questionIdCounter,
                    question: q.question,
                    required: q.required
                });
                renderQuestion(questionIdCounter, q.question);
            });
            
            document.getElementById('customQuestionsData').value = JSON.stringify(customQuestions);
        }
    }
});

// // Load existing speakers
document.addEventListener('DOMContentLoaded', function() {
    const existingSpeakersJson = '{{ existing_speakers_json|safe }}';
    
    if (existingSpeakersJson && existingSpeakersJson !== '[]') {
        const existingSpeakers = JSON.parse(existingSpeakersJson);
        
        if (existingSpeakers.length > 0) {
            selectedSpeakersData = existingSpeakers.map(function(s) {
                // Build full name
                const titles = {'mr': 'Mr.', 'mrs': 'Mrs.', 'ms': 'Ms.', 'dr': 'Dr.', 'prof': 'Prof.'};
                const parts = [];
                if (s.title) parts.push(titles[s.title]);
                if (s.first_name) parts.push(s.first_name);
                if (s.middle_name) parts.push(s.middle_name);
                if (s.last_name) parts.push(s.last_name);
                
                return {
                    id: s.id,
                    full_name: parts.join(' '),
                    designation: s.designation || '',
                    company: s.company || '',
                    photo_url: s.photo ? '/media/' + s.photo : null
                };
            });
            
            updateSelectedSpeakersDisplay();
            updateHiddenInput();
        }
    }
});


