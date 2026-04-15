document.querySelectorAll('select').forEach(function(s){ 
    if (!s.closest('#speakerModal') && !s.classList.contains('no-select2')) {
        s.classList.add('select2');
    }
});

document.addEventListener('DOMContentLoaded', function() {
    if (typeof $ !== 'undefined' && typeof $.fn.select2 !== 'undefined') {
        $('.select2').select2({ theme: 'bootstrap-5', width: '100%' });
    }
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

    // Venue Fields
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
        } else {
            venueWrapper.style.display = "block";
            virtualWrapper.style.display = "block";
            maxPhyWrapper.style.display = "block";
            maxVirtWrapper.style.display = "block";
        }
    }

    typeRadios.forEach(radio => radio.addEventListener("change", toggleFields));
    toggleFields();
});

// ============================================================================
// GLOBAL VARIABLES 
// ============================================================================
let customQuestions = [];
let questionIdCounter = 0;
let selectedSpeakersData = [];
let allSpeakers = [];

// ============================================================================
// CUSTOM QUESTIONS MANAGEMENT
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    const enableCheckbox = document.getElementById('enableCustomQuestions');
    const questionsSection = document.getElementById('customQuestionsSection');
    const questionInput = document.getElementById('questionInput');
    const addQuestionBtn = document.getElementById('addQuestionBtn');
    const questionsList = document.getElementById('questionsList');
    const customQuestionsData = document.getElementById('customQuestionsData');

    enableCheckbox.addEventListener('change', function() {
        if (this.checked) {
            questionsSection.style.display = 'block';
        } else {
            questionsSection.style.display = 'none';
            customQuestions = [];
            questionsList.innerHTML = '';
            customQuestionsData.value = '';
        }
    });

    addQuestionBtn.addEventListener('click', addQuestion);
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

        const questionId = ++questionIdCounter;
        customQuestions.push({
            id: questionId,
            question: questionText,
            required: true
        });

        customQuestionsData.value = JSON.stringify(customQuestions);
        renderQuestion(questionId, questionText);
        questionInput.value = '';
        questionInput.focus();
    }

    function renderQuestion(id, text) {
        const card = document.createElement('div');
        card.className = 'card mb-2';
        card.id = `question-${id}`;
        card.innerHTML = `
            <div class="card-body p-3">
                <div class="d-flex justify-content-between">
                    <div class="flex-grow-1">
                        <span class="badge bg-primary me-2">Q${customQuestions.length}</span>
                        <strong>${escapeHtml(text)}</strong>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeQuestion(${id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        questionsList.appendChild(card);
    }

    window.removeQuestion = function(id) {
        if (confirm('Remove this question?')) {
            customQuestions = customQuestions.filter(q => q.id !== id);
            customQuestionsData.value = JSON.stringify(customQuestions);
            document.getElementById(`question-${id}`).remove();
        }
    };

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});

// ============================================================================
// SPEAKER MODAL FUNCTIONALITY
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    const speakerModal = document.getElementById('speakerModal');
    const speakersListContainer = document.getElementById('speakers-list-container');
    const selectedSpeakersList = document.getElementById('selected-speakers-list');
    const speakerIdsInput = document.getElementById('speaker_ids');
    const addSelectedBtn = document.getElementById('add-selected-speaker-btn');
    const createSpeakerBtn = document.getElementById('create-speaker-btn');
    const createSpeakerForm = document.getElementById('create-speaker-form');
    const speakerSearch = document.getElementById('speaker-search');
    
    let selectedSpeakerInModal = null;
    
    updateSelectedSpeakersDisplay();
    
    speakerModal.addEventListener('show.bs.modal', function() {
        loadSpeakers();
    });
    
    document.getElementById('select-speaker-tab').addEventListener('click', function() {
        addSelectedBtn.style.display = 'inline-block';
        createSpeakerBtn.style.display = 'none';
    });
    
    document.getElementById('create-speaker-tab').addEventListener('click', function() {
        addSelectedBtn.style.display = 'none';
        createSpeakerBtn.style.display = 'inline-block';
    });
    
    function loadSpeakers() {
        fetch(`/conference/speakers/list/`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    allSpeakers = data.speakers;
                    displaySpeakers(allSpeakers);
                }
            })
            .catch(error => console.error('Error:', error));
    }
    
    // NEW: Display speakers WITH AVATARS
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
            
            html += `
                <div class="list-group-item list-group-item-action speaker-list-item ${isSelected ? 'selected' : ''}" 
                     onclick="selectSpeaker(${speaker.id})" 
                     style="cursor:pointer;">
                    <div class="d-flex align-items-center">
                        <!-- AVATAR -->
                        ${speaker.photo_url ? `
                            <img src="${speaker.photo_url}" 
                                 alt="${speaker.full_name}" 
                                 class="speaker-avatar me-3"
                                 style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;">
                        ` : `
                            <div class="speaker-avatar me-3 bg-secondary text-white d-flex align-items-center justify-content-center"
                                 style="width: 50px; height: 50px; border-radius: 50%; font-size: 1.2rem;">
                                ${speaker.full_name.charAt(0).toUpperCase()}
                            </div>
                        `}
                        
                        <!-- SPEAKER INFO -->
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
                        
                        <!-- SELECTION BADGE -->
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

    
    if (speakerSearch) {
        speakerSearch.addEventListener('input', function() {
            const term = this.value.toLowerCase();
            const filtered = allSpeakers.filter(s => 
                s.full_name.toLowerCase().includes(term) ||
                (s.company && s.company.toLowerCase().includes(term))
            );
            displaySpeakers(filtered);
        });
    }
    
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
                headers: {'X-CSRFToken': formData.get('csrfmiddlewaretoken')}
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    selectedSpeakersData.push(data.speaker);
                    allSpeakers.push(data.speaker);
                    updateSelectedSpeakersDisplay();
                    updateHiddenInput();
                    displaySpeakers(allSpeakers);
                    createSpeakerForm.reset();
                    bootstrap.Modal.getInstance(speakerModal).hide();
                }
            })
            .finally(() => {
                btn.disabled = false;
                btnText.textContent = 'Create & Add Speaker';
                spinner.classList.add('d-none');
            });
        });
    }
    
    function updateSelectedSpeakersDisplay() {
        if (selectedSpeakersData.length === 0) {
            selectedSpeakersList.innerHTML = '<div class="col-12"><p class="text-muted mb-0">No speakers added yet.</p></div>';
            return;
        }
        
        let html = '';
        selectedSpeakersData.forEach(speaker => {
            html += `
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-body position-relative">
                            <button type="button" class="btn btn-sm btn-danger position-absolute top-0 end-0 m-2" 
                                    onclick="removeSpeaker(${speaker.id})" title="Remove">
                                <i class="fas fa-times"></i>
                            </button>
                            <h6 class="mb-1">${speaker.full_name}</h6>
                            ${speaker.designation ? `<small class="text-muted">${speaker.designation}</small>` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
        selectedSpeakersList.innerHTML = html;
    }
    
    window.removeSpeaker = function(speakerId) {
        if (confirm('Remove this speaker?')) {
            selectedSpeakersData = selectedSpeakersData.filter(s => s.id !== speakerId);
            updateSelectedSpeakersDisplay();
            updateHiddenInput();
            displaySpeakers(allSpeakers);
        }
    };
    
    function updateHiddenInput() {
        speakerIdsInput.value = selectedSpeakersData.map(s => s.id).join(',');
    }
});

// ============================================================================
// LOAD EXISTING CUSTOM QUESTIONS (FOR EDIT MODE)
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    const existingQuestionsJson = '{{ existing_questions_json|safe }}';
    
    if (existingQuestionsJson && existingQuestionsJson !== '[]') {
        try {
            const existingQuestions = JSON.parse(existingQuestionsJson);
            
            if (existingQuestions.length > 0) {
                document.getElementById('enableCustomQuestions').checked = true;
                document.getElementById('customQuestionsSection').style.display = 'block';
                
                existingQuestions.forEach(function(q) {
                    questionIdCounter++;
                    customQuestions.push({
                        id: questionIdCounter,
                        question: q.question,
                        required: q.required
                    });
                    
                    const card = document.createElement('div');
                    card.className = 'card mb-2';
                    card.id = `question-${questionIdCounter}`;
                    card.innerHTML = `
                        <div class="card-body p-3">
                            <div class="d-flex justify-content-between">
                                <div class="flex-grow-1">
                                    <span class="badge bg-primary me-2">Q${customQuestions.length}</span>
                                    <strong>${q.question}</strong>
                                </div>
                                <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeQuestion(${questionIdCounter})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    `;
                    document.getElementById('questionsList').appendChild(card);
                });
                
                document.getElementById('customQuestionsData').value = JSON.stringify(customQuestions);
            }
        } catch (e) {
            console.error('Error loading questions:', e);
        }
    }
});

// ============================================================================
// LOAD EXISTING SPEAKERS (FOR EDIT MODE)
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    const existingSpeakersJson = '{{ existing_speakers_json|safe }}';
    
    if (existingSpeakersJson && existingSpeakersJson !== '[]') {
        try {
            const existingSpeakers = JSON.parse(existingSpeakersJson);
            
            if (existingSpeakers.length > 0) {
                selectedSpeakersData = existingSpeakers.map(function(s) {
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
                
                const selectedSpeakersList = document.getElementById('selected-speakers-list');
                const speakerIdsInput = document.getElementById('speaker_ids');
                
                let html = '';
                selectedSpeakersData.forEach(speaker => {
                    html += `
                        <div class="col-md-6">
                            <div class="card">
                                <div class="card-body position-relative">
                                    <button type="button" class="btn btn-sm btn-danger position-absolute top-0 end-0 m-2" 
                                            onclick="removeSpeaker(${speaker.id})" title="Remove">
                                        <i class="fas fa-times"></i>
                                    </button>
                                    <h6 class="mb-1">${speaker.full_name}</h6>
                                    ${speaker.designation ? `<small class="text-muted">${speaker.designation}</small>` : ''}
                                </div>
                            </div>
                        </div>
                    `;
                });
                selectedSpeakersList.innerHTML = html;
                speakerIdsInput.value = selectedSpeakersData.map(s => s.id).join(',');
            }
        } catch (e) {
            console.error('Error loading speakers:', e);
        }
    }
});
