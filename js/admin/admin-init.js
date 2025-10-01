$(document).ready(function () {
    // Header load
    $("#header-placeholder").load("static/header.html");
    // Admin nav load
    $("#nav-admin-placeholder").load("static/nav_admin.html", function() {
        // Trigger an event when nav is loaded
        $(document).trigger('adminNavLoaded');
    });
});