$(document).ready(function () {
    // Header load
    $("#header-placeholder").load("/syndoriamiku.github.io/static/header.html");
    // Admin nav load
    $("#nav-admin-placeholder").load("/syndoriamiku.github.io/static/nav_admin.html", function() {
        // Trigger an event when nav is loaded
        $(document).trigger('adminNavLoaded');
    });
});