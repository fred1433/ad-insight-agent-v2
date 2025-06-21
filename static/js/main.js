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
    const settingsModal = document.getElementById('settings-modal');
    if (settingsModal) {
        const closeModalButton = settingsModal.querySelector('.close-button');

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
    }

    // --- HTMX Event Listeners ---
    document.body.addEventListener('htmx:afterSwap', function(event) {
        // After loading settings form, show the modal
        if (event.detail.target.id === 'settings-form-container') {
            const settingsModal = document.getElementById('settings-modal');
            const userDropdown = document.getElementById('user-dropdown');
            
            if (settingsModal) settingsModal.style.display = 'block';
            if (userDropdown) userDropdown.classList.remove('show');
        }
        
        // After loading content in the generic info modal, show it
        if (event.detail.target.id === 'modal-content-dynamic') {
            const modal = document.getElementById('infoModal');
            modal.style.display = 'block';

            // Logic for advanced options toggle
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

    // --- HTMX Modal Control ---
    document.body.addEventListener('closeModal', function(evt) {
        if (evt.detail && evt.detail.value) {
            const modalToClose = document.getElementById(evt.detail.value);
            if (modalToClose) {
                modalToClose.style.display = 'none';
            }
        }
    });

    // Écouteur pour vider le champ de la clé API
    document.body.addEventListener('clearApiKeyInput', function() {
        const apiKeyInput = document.getElementById('gemini_api_key');
        if (apiKeyInput) {
            apiKeyInput.value = '';
        }
    });

    // --- Contrôle de la Modale Générique ---
    /* MOVED TO A CENTRAL HTMX LISTENER */

    // --- Contrôle de la Modale ---
    const modal = document.getElementById('infoModal');
}); 