$(document).ready(function () {
    // Check if user is already logged in and redirect to home
    checkAuthAndRedirect();
    
    $("input[required]").each(function () {
        $(this).on("blur", function () {
            if ($(this).val().trim() === "") {
                $(this).addClass("input-error");
            }
        });

        $(this).on("input", function () {
            if ($(this).val().trim() !== "") {
                $(this).removeClass("input-error");
            }
        });
    });
});

/**
 * Check if user is already authenticated and redirect to home if true
 */
function checkAuthAndRedirect() {
    const token = localStorage.getItem('access');
    
    if (token) {
        try {
            // Get the payload part of the JWT token (second part)
            const payload = token.split('.')[1];
            // Decode the base64 payload
            const decodedPayload = JSON.parse(atob(payload));
            
            // Check if token is not expired
            const currentTime = Math.floor(Date.now() / 1000);
            if (decodedPayload.exp && decodedPayload.exp > currentTime) {
                // Token is valid, redirect to home
                window.location.href = "/";
                return;
            } else {
                // Token is expired, remove it
                localStorage.removeItem('access');
                localStorage.removeItem('refresh');
            }
        } catch (error) {
            console.error('Error decoding token:', error);
            // Invalid token, remove it
            localStorage.removeItem('access');
            localStorage.removeItem('refresh');
        }
    }
}
