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
}); 