$(document).ready(function () {
    console.log("init.js loaded successfully");
    console.log("Current location:", window.location.href);
    
    // Determine the correct path to static files based on current location
    var currentPath = window.location.pathname;
    var staticPath = "";
    
    // If we're in a subdirectory, we need to go up one level
    if (currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
        currentPath.includes('/user/') || currentPath.includes('/admin/') || 
        currentPath.includes('/gacha/')) {
        staticPath = "../static/";
        console.log("Using subdirectory path:", staticPath);
    } else {
        staticPath = "./static/";
        console.log("Using root path:", staticPath);
    }
    
    // Load static components with error handling
    $("#dialog-placeholder").load(staticPath + "dialog_notice.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load dialog_notice.html:", xhr.status, xhr.statusText);
        } else {
            console.log("Successfully loaded dialog_notice.html");
        }
    });
    
    $("#spinner-placeholder").load(staticPath + "spinner.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load spinner.html:", xhr.status, xhr.statusText);
        } else {
            console.log("Successfully loaded spinner.html");
        }
    });
    
    $("#header-placeholder").load(staticPath + "header.html", function(response, status, xhr) {
        if (status == "error") {
            console.error("Failed to load header.html:", xhr.status, xhr.statusText);
        } else {
            console.log("Successfully loaded header.html");
            // Initialize header actions after header is loaded
            if (typeof initializeHeaderActions === 'function') {
                console.log("Calling initializeHeaderActions after header load");
                initializeHeaderActions();
            } else {
                console.log("initializeHeaderActions function not found, will try later");
            }
        }
    });
});
