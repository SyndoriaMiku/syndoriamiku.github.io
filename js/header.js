$(document).ready(function () {
    const token = localStorage.getItem("access_token");
    const $headerActions = $("#header-actions");

    if (token) {
        // Nếu đã đăng nhập → Hiển thị Profile & Logout
        $headerActions.html(`
            <button class="header-btn" id="profile-btn">Trang cá nhân</button>
            <button class="header-btn" id="logout-btn">Đăng xuất</button>
        `);

        $("#logout-btn").on("click", function () {
            logout();
        });

        $("#profile-btn").on("click", function () {
            window.location.href = "user/profile.html"; // Bạn có thể sửa lại nếu cần
        });

    } else {
        // Nếu chưa đăng nhập → Hiển thị Login & Register
        $headerActions.html(`
            <button class="header-btn" id="login-btn">Đăng nhập</button>
            <button class="header-btn" id="register-btn">Đăng ký</button>
        `);

        $("#login-btn").on("click", function () {
            window.location.href = "/syndoriamiku.github.io/user/login.html";
        });

        $("#register-btn").on("click", function () {
            window.location.href = "/syndoriamiku.github.io/user/register.html";
        });
    }
});

function logout() {
    const refreshToken = localStorage.getItem("refresh_token");

    if (!refreshToken) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token ");
        window.location.href = "/syndoriamiku.github.io/user/login.html";
        return;
    }

    $.ajax({
        url: "https://gremory.pythonanywhere.com/api/logout/", // Đổi lại nếu URL khác
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({
            refresh: refreshToken
        }),
        success: function (response) {
            showNoticeDialog(response.message || "Đăng xuất thành công");

            // Xóa token ở localStorage
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");

            // Điều hướng về trang đăng nhập
            window.location.href = "/syndoriamiku.github.io/user/login.html";
        },
        error: function (xhr) {
            console.error("Lỗi khi logout:", xhr.responseJSON || xhr.statusText);

            // Dù lỗi vẫn xóa token localStorage và điều hướng
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");

            window.location.href = "/syndoriamiku.github.io/user/login.html";
        }
    });
}

