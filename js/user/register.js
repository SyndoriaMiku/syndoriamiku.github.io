$(document).ready(function () {
    //Register button click
    $("#register-button").click(function () {
        register();
    });

    //Enter key press in input fields
    $("#register-username, #register-password, #register-confirm-password").keypress(function (e) {
        if (e.which === 13) { // Enter key pressed
            register();
        }
    });

    // Toggle password visibility for main password field
    $("#toggle-reg-password").click(function() {
        const passwordField = $("#reg-password");
        const eyeIcon = $("#reg-eye-icon");
        
        if (passwordField.attr("type") === "password") {
            passwordField.attr("type", "text");
            eyeIcon.text("🙈"); // Hide eye icon
        } else {
            passwordField.attr("type", "password");
            eyeIcon.text("👁️"); // Show eye icon
        }
    });

    // Toggle password visibility for confirm password field
    $("#toggle-reg-confirm").click(function() {
        const confirmField = $("#reg-confirm");
        const eyeIcon = $("#reg-confirm-eye-icon");
        
        if (confirmField.attr("type") === "password") {
            confirmField.attr("type", "text");
            eyeIcon.text("🙈"); // Hide eye icon
        } else {
            confirmField.attr("type", "password");
            eyeIcon.text("👁️"); // Show eye icon
        }
    });
});

/**
 * Register function
 */
function register() {
    const username = $("#reg-username").val().trim();
    const password = $("#reg-password").val().trim();
    const confirmPassword = $("#reg-confirm").val().trim();
    
    if (!username || !password || !confirmPassword) {
        showNoticeDialog("Vui lòng nhập đầy đủ thông tin!");
        return;
    }
    if (password !== confirmPassword) {
        showNoticeDialog("Mật khẩu xác nhận không khớp!");
        return;
    }
    
    showSpinner(); // Hiện spinner
    $.ajax({
        type: "POST",
        url: "https://gremory.pythonanywhere.com/api/register/",
        data: {
            username: username,
            password: password
        },
        success: function (response) {
            // After successful registration, perform login
            autoLogin(username, password);
        },
        error: function (error) {
            hideSpinner(); // Ẩn spinner
            if (error.responseJSON) {
                showNoticeDialog("Đăng ký thất bại: " + error.responseJSON.message);
            } else {
                showNoticeDialog("Đăng ký thất bại! Vui lòng thử lại.");
            }
        }
    });
}

/**
 * Auto login after successful registration
 * @param {string} username 
 * @param {string} password 
 */
function autoLogin(username, password) {
    $.ajax({
        type: "POST",
        url: "https://gremory.pythonanywhere.com/api/login/",
        data: {
            username: username,
            password: password
        },
        success: function (response) {
            if (response.access) {
                localStorage.setItem("access", response.access);
                // Decode token to check admin status
                const payload = JSON.parse(atob(response.access.split('.')[1]));
                const isAdmin = payload.is_staff === true;
                
                if (response.refresh) {
                    localStorage.setItem("refresh", response.refresh);
                }
                if (response.username) {
                    localStorage.setItem("username", response.username);
                }
                
                hideSpinner();
                showNoticeDialog("Đăng ký và đăng nhập thành công!");

                // Redirect after showing message
                setTimeout(function() {
                    if (isAdmin) {
                        navigateToPage("/admin/index");
                    } else {
                        navigateToPage("/");
                    }
                }, 1000);
            } else {
                hideSpinner();
                showNoticeDialog("Đăng ký thành công nhưng đăng nhập thất bại. Vui lòng đăng nhập thủ công.");
                setTimeout(function() {
                    navigateToPage("user/login");
                }, 2000);
            }
        },
        error: function (error) {
            hideSpinner();
            showNoticeDialog("Đăng ký thành công nhưng đăng nhập thất bại. Vui lòng đăng nhập thủ công.");
            setTimeout(function() {
                navigateToPage("user/login");
            }, 2000);
        }
    });
}