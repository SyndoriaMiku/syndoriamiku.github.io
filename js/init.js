$(document).ready(function () {
    // Determine the correct path to static files based on current location
    var currentPath = window.location.pathname;
    var staticPath = "";
    
    // If we're in a subdirectory, we need to go up one level
    if (currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
        currentPath.includes('/user/') || currentPath.includes('/admin/') || 
        currentPath.includes('/gacha/')) {
        staticPath = "../static/";
    } else {
        staticPath = "./static/";
    }
    
    // Load static components with error handling
    $("#dialog-placeholder").load(staticPath + "dialog_notice.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load dialog_notice.html:", xhr.status, xhr.statusText);
        }
    });
    
    $("#spinner-placeholder").load(staticPath + "spinner.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load spinner.html:", xhr.status, xhr.statusText);
        }
    });
    
    $("#header-placeholder").load(staticPath + "header.html", function(response, status, xhr) {
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
    $("#nav-placeholder").load(staticPath + "nav_home.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load nav_home.html:", xhr.status, xhr.statusText);
        } else {
            // Set active navigation item based on current path
            var $nav = $("#nav-placeholder");
            
            if (currentPath.includes('/ytg/')) {
                // YTG pages
                $nav.find('a[href="/ytg/"]').addClass('active');
            } else if (currentPath.includes('/temple/')) {
                // Temple pages
                $nav.find('a[href="/temple/"]').addClass('active');
            } else {
                // Home page (default for all other pages including root)
                $nav.find('a[href="/"]').addClass('active');
            }
        }
    });
});
