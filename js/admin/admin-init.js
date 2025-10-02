$(document).ready(function () {
    // Load static components
    $("#dialog-placeholder").load("/static/dialog_notice.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load dialog_notice.html:", xhr.status, xhr.statusText);
        }
    });
    
    $("#spinner-placeholder").load("/static/spinner.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load spinner.html:", xhr.status, xhr.statusText);
        }
    });
    
    // Header load
    $("#header-placeholder").load("/static/header.html");
    // Admin nav load
    $("#nav-admin-placeholder").load("/static/nav_admin.html", function() {
        // Trigger an event when nav is loaded
        $(document).trigger('adminNavLoaded');
    });
});