// Function to initialize header actions - called after header is loaded
function initializeHeaderActions() {
    console.log("=== initializeHeaderActions called ===");
    const token = localStorage.getItem("access");
    const $headerActions = $("#header-actions");

    console.log("Header actions element found:", $headerActions.length > 0);
    console.log("Token exists:", token ? "YES" : "NO");

    if ($headerActions.length === 0) {
        console.error("❌ Header actions element not found!");
        return;
    }

    if (token) {
        console.log("👤 User is logged in");
        try {
            // Decode token to get nickname
            const payload = JSON.parse(atob(token.split('.')[1]));
            const nickname = payload.nickname || payload.username || "User";
            
            // Show logged in state
            $headerActions.html(`
                <button class="header-btn" id="profile-btn" style="margin-right: 10px;">Xin chào, ${nickname}</button>
                <button class="header-btn" id="logout-btn">Đăng xuất</button>
            `);

            console.log("✅ Logged in buttons added for:", nickname);

            // Add event listeners
            $("#logout-btn").off('click').on("click", function () {
                console.log("Logout clicked");
                logout();
            });

            $("#profile-btn").off('click').on("click", function () {
                console.log("Profile clicked");
                var targetPath = getRelativePath("user/profile.html");
                window.location.href = targetPath;
            });

        } catch (error) {
            console.error("❌ Error decoding token:", error);
            localStorage.removeItem("access");
            localStorage.removeItem("refresh");
            showLoginButtons($headerActions);
        }
    } else {
        console.log("🔑 User is not logged in");
        showLoginButtons($headerActions);
    }
}

function showLoginButtons($headerActions) {
    console.log("🔑 Showing login/register buttons");
    
    $headerActions.html(`
        <button class="header-btn" id="login-btn" style="margin-right: 10px;">Đăng nhập</button>
        <button class="header-btn" id="register-btn">Đăng ký</button>
    `);

    console.log("✅ Login/register buttons added to DOM");

    // Add event listeners with debugging
    $("#login-btn").off('click').on("click", function () {
        console.log("Login button clicked");
        var targetPath = getRelativePath("user/login.html");
        console.log("Redirecting to:", targetPath);
        window.location.href = targetPath;
    });

    $("#register-btn").off('click').on("click", function () {
        console.log("Register button clicked");
        var targetPath = getRelativePath("user/register.html");
        console.log("Redirecting to:", targetPath);
        window.location.href = targetPath;
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
    
    console.log("Current path:", currentPath, "→ Target:", relativePath);
    return relativePath;
}

// Simple DOM ready approach
$(document).ready(function () {
    console.log("=== header.js DOM ready ===");
    
    // Try multiple times to initialize
    function tryInitialize(attempt) {
        console.log("Attempt", attempt, "to initialize header actions");
        
        if ($("#header-actions").length > 0) {
            console.log("✅ Header actions element found, initializing...");
            initializeHeaderActions();
            return;
        }
        
        if (attempt < 10) {
            console.log("❌ Header actions not found, retrying in 500ms...");
            setTimeout(() => tryInitialize(attempt + 1), 500);
        } else {
            console.error("❌ Failed to find header actions after 10 attempts");
        }
    }
    
    // Start trying
    tryInitialize(1);
});

function logout() {
    console.log("🔓 Logout function called");
    const refreshToken = localStorage.getItem("refresh");

    if (!refreshToken) {
        console.log("No refresh token, clearing storage and redirecting");
        localStorage.removeItem("access");
        localStorage.removeItem("refresh");
        redirectToLogin();
        return;
    }

    console.log("Attempting logout via API...");
    $.ajax({
        url: "https://gremory.pythonanywhere.com/api/logout/",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({
            refresh: refreshToken
        }),
        success: function (response) {
            console.log("✅ Logout successful:", response);
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
    console.log("🔄 Redirecting to login:", targetPath);
    window.location.href = targetPath;
}

