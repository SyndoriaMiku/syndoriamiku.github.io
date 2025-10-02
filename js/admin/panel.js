$(document).ready(function () {
    //Check admin
    if (!isAdmin()) {
        window.location.href = "/user/login.html";
        return;
    }
});

// Listen for nav loaded event
$(document).on('adminNavLoaded', function() {
    //Set activate admin nav bar
    $("#nav-admin-panel").addClass("active");
});

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
        // Check if user is staff
        return decodedPayload.is_staff === true;
    } catch (error) {
        console.error('Error decoding token:', error);
        return false;
    }
}