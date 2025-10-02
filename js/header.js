// Function to initialize header actions - called after header is loaded
function initializeHeaderActions() {
    const token = localStorage.getItem("access");
    const $headerActions = $("#header-actions");

    if ($headerActions.length === 0) {
        console.error("❌ Header actions element not found!");
        return;
    }

    if (token) {
        try {
            // Decode token to get nickname
            const payload = JSON.parse(atob(token.split('.')[1]));
            const nickname = payload.nickname || payload.username || "User";
            
            // Show logged in state
            $headerActions.html(`
                <button class="header-btn" id="profile-btn" style="margin-right: 10px;">Xin chào, ${nickname}</button>
                <button class="header-btn" id="logout-btn">Đăng xuất</button>
            `);

            // Add event listeners
            $("#logout-btn").off('click').on("click", function () {
                logout();
            });

            $("#profile-btn").off('click').on("click", function () {
                var targetPath = getRelativePath("/user/profile.html");
                window.location.href = targetPath;
            });

        } catch (error) {
            console.error("❌ Error decoding token:", error);
            localStorage.removeItem("access");
            localStorage.removeItem("refresh");
            showLoginButtons($headerActions);
        }
    } else {
        showLoginButtons($headerActions);
    }
}

function showLoginButtons($headerActions) {
    $headerActions.html(`
        <button class="header-btn" id="login-btn" style="margin-right: 10px;">Đăng nhập</button>
        <button class="header-btn" id="register-btn">Đăng ký</button>
    `);

    // Add event listeners with debugging
    $("#login-btn").off('click').on("click", function () {
        window.location.href = "/user/login.html";
    });

    $("#register-btn").off('click').on("click", function () {
        window.location.href = "/user/register.html";
    });
}

function getRelativePath(targetFile) {
    var currentPath = window.location.pathname;
    var relativePath = "";
    
    if (currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
        currentPath.includes('/admin/') || currentPath.includes('/gacha/')) {
        relativePath = "../" + targetFile;
    } else {
        relativePath = targetFile;
    }
    
    return relativePath;
}

// Simple DOM ready approach
$(document).ready(function () {
    // Try multiple times to initialize
    function tryInitialize(attempt) {
        if ($("#header-actions").length > 0) {
            initializeHeaderActions();
            return;
        }
        
        if (attempt < 10) {
            setTimeout(() => tryInitialize(attempt + 1), 500);
        } else {
            console.error("❌ Failed to find header actions after 10 attempts");
        }
    }
    
    // Start trying
    tryInitialize(1);
});

function logout() {
    const refreshToken = localStorage.getItem("refresh");

    if (!refreshToken) {
        localStorage.removeItem("access");
        localStorage.removeItem("refresh");
        redirectToLogin();
        return;
    }

    $.ajax({
        url: "https://gremory.pythonanywhere.com/api/logout/",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({
            refresh: refreshToken
        }),
        success: function (response) {
            if (typeof showNoticeDialog === 'function') {
                showNoticeDialog(response.message || "Đăng xuất thành công");
            }

            localStorage.removeItem("access");
            localStorage.removeItem("refresh");
            redirectToLogin();
        },
        error: function (xhr) {
            console.error("❌ Logout error:", xhr.responseJSON || xhr.statusText);
            // Clear tokens anyway
            localStorage.removeItem("access");
            localStorage.removeItem("refresh");
            redirectToLogin();
        }
    });
}

function redirectToLogin() {
    var targetPath = getRelativePath("user/login.html");
    window.location.href = targetPath;
}

