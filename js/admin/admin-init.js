$(document).ready(function () {
    // Get base path for GitHub Pages compatibility
    const basePath = window.location.pathname.includes('syndoriamiku.github.io') ? '/syndoriamiku.github.io' : '';
    
    // Header load
    $("#header-placeholder").load(basePath + "/static/header.html");
    // Admin nav load
    $("#nav-admin-placeholder").load(basePath + "/static/nav_admin.html", function() {
        // Trigger an event when nav is loaded
        $(document).trigger('adminNavLoaded');
    });
});