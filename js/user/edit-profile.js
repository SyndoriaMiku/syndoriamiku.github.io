$(document).ready(function() {
    // Check if user is logged in first
    const token = localStorage.getItem("access");
    if (!token) {
        window.location.href = "/user/login.html";
        return;
    }
    
    // Decode JWT token to get username
    let currentUsername = null;
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        currentUsername = payload.username;
    } catch (error) {
        console.error("Failed to decode token:", error);
        window.location.href = "/user/login.html";
        return;
    }
    
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
                showNoticeDialog("Thay đổi nickname thành công!");
                $('#new-username').val(''); // Clear the form
                
                // Optional: Update the profile display if needed
                setTimeout(function() {
                    window.location.href = "/user/profile.html";
                }, 2000);
            },
            error: function(xhr, status, error) {
                hideSpinner();
                let errorMessage = "Thay đổi nickname thất bại";
                
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
            showNoticeDialog("Vui lòng điền tất cả các trường mật khẩu!");
            return;
        }
        
        if (newPassword !== confirmPassword) {
            showNoticeDialog("Mật khẩu mới không khớp");
            return;
        }
        
        if (newPassword.length < 8) {
            showNoticeDialog("Mật khẩu phải ít nhất 8 ký tự");
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
                showNoticeDialog("Thay đổi mật khẩu thành công!");
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
                let errorMessage = "Thay đổi mật khẩu thất bại!";
                
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
            $("#current-username").val(response.nickname || currentUsername);
        },
        error: function(xhr, status, error) {
            console.error("Failed to load user data:", error);
            // Don't redirect on error, just leave the current nickname field empty
        }
    });
}