$(document).ready(function () {
    // Admin access is already checked in admin-init.js
    // No additional check needed here
});

// Listen for nav loaded event
$(document).on('adminNavLoaded', function() {
    //Set activate admin nav bar
    $("#nav-admin-panel").addClass("active");
});