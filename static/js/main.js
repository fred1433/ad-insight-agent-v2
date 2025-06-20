document.addEventListener('DOMContentLoaded', function() {
    const userMenuTrigger = document.getElementById('user-menu-trigger');
    const userDropdown = document.getElementById('user-dropdown');

    if (userMenuTrigger) {
        userMenuTrigger.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation(); // Prevents the window click event from firing immediately
            userDropdown.classList.toggle('show');
        });
    }

    // Close the dropdown if the user clicks outside of it
    window.addEventListener('click', function(event) {
        if (userDropdown && userDropdown.classList.contains('show')) {
            if (!userMenuTrigger.contains(event.target)) {
                userDropdown.classList.remove('show');
            }
        }
    });

    // --- Settings Modal Logic ---
    const settingsLink = document.getElementById('settings-link');
    const settingsModal = document.getElementById('settings-modal');
    const closeModalButton = settingsModal.querySelector('.close-button');

    if (settingsLink) {
        settingsLink.addEventListener('click', function(event) {
            event.preventDefault();
            settingsModal.style.display = 'block';
            // Close the dropdown menu as well
            if (userDropdown) {
                userDropdown.classList.remove('show');
            }
        });
    }

    if (closeModalButton) {
        closeModalButton.addEventListener('click', function() {
            settingsModal.style.display = 'none';
        });
    }

    // Close the modal if clicking outside of it
    window.addEventListener('click', function(event) {
        if (event.target == settingsModal) {
            settingsModal.style.display = 'none';
        }
    });

    // --- HTMX Modal Control ---
    document.body.addEventListener('closeModal', function(evt) {
        const modalToClose = document.getElementById(evt.detail.value);
        if (modalToClose) {
            modalToClose.style.display = 'none';
        }
    });

    // Écouteur pour vider le champ de la clé API
    document.body.addEventListener('clearApiKeyInput', function() {
        const apiKeyInput = document.getElementById('gemini_api_key');
        if (apiKeyInput) {
            apiKeyInput.value = '';
        }
    });

    // --- Client-side validation for Settings Form ---
    const settingsForm = document.getElementById('settings-form');
    if (settingsForm) {
        settingsForm.addEventListener('submit', function(event) {
            const apiKeyInput = document.getElementById('gemini_api_key');
            const feedbackDiv = document.getElementById('settings-feedback');
            const apiKey = apiKeyInput.value.trim();

            if (apiKey.startsWith('AIza') && apiKey.length > 20) {
                // Key seems valid, let the form submit
                feedbackDiv.innerHTML = ''; // Clear previous errors
                return;
            } else {
                // Key is invalid, prevent submission and show error
                event.preventDefault();
                feedbackDiv.innerHTML = '<small class="text-danger">❌ Clave no válida. Debe empezar con "AIza" y tener más de 20 caracteres.</small>';
            }
        });
    }

    // --- Contrôle de la Modale Générique ---
    document.body.addEventListener('htmx:afterSwap', function(event) {
        // S'assurer que le contenu a été chargé dans la modale d'info
        if (event.detail.target.id === 'modal-content-dynamic') {
            const modal = document.getElementById('infoModal');
            modal.style.display = 'block';

            // Logique pour le déploiement des options avancées
            const toggleLink = document.getElementById('advanced-options-toggle');
            const advancedOptions = document.getElementById('advanced-options');

            if (toggleLink && advancedOptions) {
                toggleLink.addEventListener('click', function(e) {
                    e.preventDefault();
                    const isHidden = advancedOptions.style.display === 'none';
                    advancedOptions.style.display = isHidden ? 'block' : 'none';
                    toggleLink.textContent = isHidden ? '- Ocultar Opciones' : '+ Opciones Avanzadas';
                });
            }
        }
    });

    // --- Contrôle de la Modale ---
    const modal = document.getElementById('infoModal');
}); 