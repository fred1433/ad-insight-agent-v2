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

    // We will add the logic for the settings modal here later
}); 