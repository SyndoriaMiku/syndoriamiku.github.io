$(document).ready(function () {
    // Load static components with error handling
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
    
    $("#header-placeholder").load("/static/header.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load header.html:", xhr.status, xhr.statusText);
        } else {
            // Initialize header actions after header is loaded
            if (typeof initializeHeaderActions === 'function') {
                initializeHeaderActions();
            }
        }
    });
    
    // Load navigation and set active state
    $("#nav-placeholder").load("/static/nav_home.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load nav_home.html:", xhr.status, xhr.statusText);
        } else {
            // Set active navigation item based on current path
            var $nav = $("#nav-placeholder");
            var currentPath = window.location.pathname;
            
            if (currentPath.includes('/ytg/')) {
                // YTG pages
                $nav.find('a[href="/ytg/"]').addClass('active');
            } else if (currentPath.includes('/temple/')) {
                // Temple pages
                $nav.find('a[href="/temple/"]').addClass('active');
            } else if (currentPath === '/' || currentPath === '/index.html') {
                // Home page (only for root folder)
                $nav.find('a[href="/"]').addClass('active');
            }
            // No active class added for other pages (user, admin, gacha, etc.)
        }
    });
});
