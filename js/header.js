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
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
            window.location.href = "user/login.html";
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
            window.location.href = "user/login.html";
        });

        $("#register-btn").on("click", function () {
            window.location.href = "user/register.html";
        });
    }
});
