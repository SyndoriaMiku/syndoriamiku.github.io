$(document).ready(function() {
    // Login button click event
    $("#login-button").click(function() {
        login();
    });

    //Enter key press in input fields
    $("#login-username, #login-password").keypress(function(e) {
        if (e.which === 13) { // Enter key pressed
            login();
        }
    });

    // Toggle password visibility
    $("#toggle-password").click(function() {
        const passwordField = $("#login-password");
        const eyeIcon = $("#eye-icon");
        
        if (passwordField.attr("type") === "password") {
            passwordField.attr("type", "text");
            eyeIcon.attr("src", "/static/show.png"); // Show eye icon when password is visible
        } else {
            passwordField.attr("type", "password");
            eyeIcon.attr("src", "/static/invisible.png"); // Hide eye icon when password is hidden
        }
    });
});

/**
 * Login function
 */

function login() {
    const username = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;

    if (!username || !password) {
        showNoticeDialog("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu!");
        return;
    }

    showSpinner(); // Hiện spinner
    
    $.ajax({
        type: "POST",
        url: "https://gremory.pythonanywhere.com/api/login/",
        data: {
            username: username,
            password: password
        },
        success: function (response) {
            if (response.access) {
                localStorage.setItem("access", response.access);  // Changed to match admin panel key
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

                // Redirect based on decoded token's is_staff
                if (isAdmin) {
                    window.location.href = "/admin/";
                } else {
                    window.location.href = "/";
                }
            } else {
                showNoticeDialog("Lỗi: Token không hợp lệ!");
                hideSpinner();
            }
        },
        error: function (error) {
            let errorMessage = "Đăng nhập thất bại!";
            if (error.responseJSON && error.responseJSON.detail) {
                errorMessage += " " + error.responseJSON.detail;
            }
            showNoticeDialog(errorMessage);
            hideSpinner();
        }
    })
}