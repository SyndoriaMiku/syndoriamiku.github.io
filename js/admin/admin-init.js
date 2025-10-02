$(document).ready(function () {
    // Check admin access before loading any content
    checkAdminAccess();
    
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

/**
 * Check admin access and redirect if necessary
 */
function checkAdminAccess() {
    const token = localStorage.getItem('access');
    
    // No token - redirect to login
    if (!token) {
        window.location.href = "/user/login.html";
        return;
    }
    
    try {
        // Get the payload part of the JWT token (second part)
        const payload = token.split('.')[1];
        // Decode the base64 payload
        const decodedPayload = JSON.parse(atob(payload));
        
        // Check if token is not expired
        const currentTime = Math.floor(Date.now() / 1000);
        if (decodedPayload.exp && decodedPayload.exp <= currentTime) {
            // Token is expired, remove it and redirect to login
            localStorage.removeItem('access');
            localStorage.removeItem('refresh');
            window.location.href = "/user/login.html";
            return;
        }
        
        // Check if user is admin
        if (decodedPayload.is_staff !== true) {
            // User is logged in but not admin - show dialog and redirect to home
            showAdminPermissionDialog();
            return;
        }
        
        // User is valid admin - allow access
        
    } catch (error) {
        console.error('Error decoding token:', error);
        // Invalid token, remove it and redirect to login
        localStorage.removeItem('access');
        localStorage.removeItem('refresh');
        window.location.href = "/user/login.html";
        return;
    }
}

/**
 * Show dialog for insufficient admin permissions and redirect after delay
 */
function showAdminPermissionDialog() {
    // Wait for dialog placeholder to be loaded, then show dialog
    const checkDialog = setInterval(function() {
        if ($("#dialog-message").length > 0) {
            clearInterval(checkDialog);
            showNoticeDialog("You need admin permission to access this page.");
            
            // Redirect to home after 3 seconds
            setTimeout(function() {
                window.location.href = "/";
            }, 3000);
        }
    }, 100);
}

/**
 * Check if user is admin by decoding the JWT token and checking is_staff
 * @returns {boolean}
 */
function isAdmin() {
    const token = localStorage.getItem('access');
    if (!token) {
        return false;
    }
    
    try {
        // Get the payload part of the JWT token (second part)
        const payload = token.split('.')[1];
        // Decode the base64 payload
        const decodedPayload = JSON.parse(atob(payload));
        
        // Check if token is not expired
        const currentTime = Math.floor(Date.now() / 1000);
        if (decodedPayload.exp && decodedPayload.exp <= currentTime) {
            return false;
        }
        
        // Check if user is staff
        return decodedPayload.is_staff === true;
    } catch (error) {
        console.error('Error decoding token:', error);
        return false;
    }
}