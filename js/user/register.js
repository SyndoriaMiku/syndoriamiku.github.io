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
            hideSpinner(); // Ẩn spinner
            showNoticeDialog("Đăng ký thành công! Vui lòng đăng nhập.");
            //Redirect to login after 2 seconds
            setTimeout(function () {
                window.location.href = "/syndoriamiku.github.io/user/login.html";
            }, 2000);
        },
        error: function (error) {
            hideSpinner(); // Ẩn spinner
            if (error.responseJSON && error.responseJSON.error) {
                showNoticeDialog("Đăng ký thất bại: " + error.responseJSON.error);
            } else {
                showNoticeDialog("Đăng ký thất bại! Vui lòng thử lại.");
            }
        }
    });
}