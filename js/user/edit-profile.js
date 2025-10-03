$(document).ready(function() {
    // Load current user data
    loadCurrentUserData();
    
    // Username change form handler
    $('#username-form').on('submit', function(e) {
        e.preventDefault();
        
        const newUsername = $('#new-username').val().trim();
        
        if (!newUsername) {
            showNoticeDialog("Please enter a new username!");
            return;
        }
        
        const token = localStorage.getItem("access");
        if (!token) {
            showNoticeDialog("You must be logged in to change your username!");
            window.location.href = "/user/login.html";
            return;
        }
        
        // Show spinner while processing
        showSpinner();
        
        $.ajax({
            type: "PATCH",
            url: "https://gremory.pythonanywhere.com/api/user/update/",
            headers: {
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json"
            },
            data: JSON.stringify({
                "nickname": newUsername
            }),
            success: function(response) {
                hideSpinner();
                showNoticeDialog("Username changed successfully!");
                $('#new-username').val(''); // Clear the form
                
                // Optional: Update the profile display if needed
                setTimeout(function() {
                    window.location.href = "/user/profile.html";
                }, 2000);
            },
            error: function(xhr, status, error) {
                hideSpinner();
                let errorMessage = "Failed to change username!";
                
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    errorMessage = xhr.responseJSON.message;
                }
                
                showNoticeDialog(errorMessage);
            }
        });
    });
    
    // Password change form handler
    $('#password-form').on('submit', function(e) {
        e.preventDefault();
        
        const currentPassword = $('#current-password').val();
        const newPassword = $('#new-password').val();
        const confirmPassword = $('#confirm-password').val();
        
        // Validation
        if (!currentPassword || !newPassword || !confirmPassword) {
            showNoticeDialog("Please fill in all password fields!");
            return;
        }
        
        if (newPassword !== confirmPassword) {
            showNoticeDialog("New passwords do not match!");
            return;
        }
        
        if (newPassword.length < 6) {
            showNoticeDialog("New password must be at least 6 characters long!");
            return;
        }
        
        const token = localStorage.getItem("access");
        if (!token) {
            showNoticeDialog("You must be logged in to change your password!");
            window.location.href = "/user/login.html";
            return;
        }
        
        // Show spinner while processing
        showSpinner();
        
        $.ajax({
            type: "PATCH",
            url: "https://gremory.pythonanywhere.com/api/user/password/change/",
            headers: {
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json"
            },
            data: JSON.stringify({
                "current_password": currentPassword,
                "new_password": newPassword
            }),
            success: function(response) {
                hideSpinner();
                showNoticeDialog("Password changed successfully!");
                
                // Clear the form
                $('#current-password').val('');
                $('#new-password').val('');
                $('#confirm-password').val('');
                
                // Redirect to profile after successful change
                setTimeout(function() {
                    window.location.href = "/user/profile.html";
                }, 2000);
            },
            error: function(xhr, status, error) {
                hideSpinner();
                let errorMessage = "Failed to change password!";
                
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    errorMessage = xhr.responseJSON.message;
                }
                
                showNoticeDialog(errorMessage);
            }
        });
    });
});

/**
 * Load current user data into the form fields.
 * @returns {void}
 */

function loadCurrentUserData() {
    const token = localStorage.getItem("access");
    if (!token) {
        window.location.href = "/user/login.html";
        return;
    }
    
    $.ajax({
        type: "GET",
        url: "https://gremory.pythonanywhere.com/api/user/",
        headers: {
            "Authorization": "Bearer " + token
        },
        success: function(response) {
            // Load current nickname into the form
            $("#current-username").val(response.nickname || response.username);
        },
        error: function(xhr, status, error) {
            console.error("Failed to load user data:", error);
            // Don't redirect on error, just leave the current nickname field empty
        }
    });
}