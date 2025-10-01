$(document).ready(function() {
    //Login button click
    $("#login-button").click(function() {
        login();
    });

    //Enter key press in input fields
    $("#login-username, #login-password").keypress(function(e) {
        if (e.which === 13) { // Enter key pressed
            login();
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
                localStorage.setItem("access_token", response.access);
            }
            if (response.refresh) {
                localStorage.setItem("refresh_token", response.refresh);
            }
            if (response.username) {
                localStorage.setItem("username", response.username);
            }
            localStorage.setItem("is_admin", response.is_admin);
            hideSpinner();

            //Redirect to home
            if (response.is_admin) {
                window.location.href = "../admin/"; 
            } else {
                window.location.href = "../";
            }


        },
        error: function (error) {
            showNoticeDialog("Đăng nhập thất bại!");
            hideSpinner();
        }
    })
}