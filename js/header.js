// Function to initialize header actions - called after header is loaded
function initializeHeaderActions() {
    console.log("Initializing header actions...");
    const token = localStorage.getItem("access");
    const $headerActions = $("#header-actions");

    if ($headerActions.length === 0) {
        console.error("Header actions element not found!");
        return;
    }

    console.log("Header actions element found, token:", token ? "exists" : "not found");

    if (token) {
        try {
            // Decode token to get nickname
            const payload = JSON.parse(atob(token.split('.')[1]));
            const nickname = payload.nickname || payload.username; // Use username if nickname is empty
            
            // Nếu đã đăng nhập → Hiển thị Hello & Logout
            $headerActions.html(`
                <button class="header-btn" id="profile-btn">Xin chào, ${nickname}</button>
                <button class="header-btn" id="logout-btn">Đăng xuất</button>
            `);

            $("#logout-btn").on("click", function () {
                logout();
            });

            $("#profile-btn").on("click", function () {
                // Determine correct path based on current location
                var currentPath = window.location.pathname;
                var targetPath = "";
                
                if (currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
                    currentPath.includes('/admin/') || currentPath.includes('/gacha/')) {
                    targetPath = "../user/profile.html";
                } else {
                    targetPath = "user/profile.html";
                }
                window.location.href = targetPath;
            });

        } catch (error) {
            console.error("Error decoding token:", error);
            // If token is invalid, clear it and show login buttons
            localStorage.removeItem("access");
            localStorage.removeItem("refresh");
            showLoginButtons($headerActions);
        }

    } else {
        showLoginButtons($headerActions);
    }
}

function showLoginButtons($headerActions) {
    // Nếu chưa đăng nhập → Hiển thị Login & Register
    $headerActions.html(`
        <button class="header-btn" id="login-btn">Đăng nhập</button>
        <button class="header-btn" id="register-btn">Đăng ký</button>
    `);

    $("#login-btn").on("click", function () {
        // Determine correct path based on current location
        var currentPath = window.location.pathname;
        var targetPath = "";
        
        if (currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
            currentPath.includes('/admin/') || currentPath.includes('/gacha/')) {
            targetPath = "../user/login.html";
        } else {
            targetPath = "user/login.html";
        }
        window.location.href = targetPath;
    });

    $("#register-btn").on("click", function () {
        // Determine correct path based on current location
        var currentPath = window.location.pathname;
        var targetPath = "";
        
        if (currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
            currentPath.includes('/admin/') || currentPath.includes('/gacha/')) {
            targetPath = "../user/register.html";
        } else {
            targetPath = "user/register.html";
        }
        window.location.href = targetPath;
    });
}

// Try to initialize when DOM is ready
$(document).ready(function () {
    console.log("header.js DOM ready");
    
    // Try to initialize immediately
    initializeHeaderActions();
    
    // Also set up a mutation observer to watch for when header is loaded
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList') {
                const headerActions = document.getElementById('header-actions');
                if (headerActions && headerActions.innerHTML.includes('<!-- Sẽ được js/header.js tự động render -->')) {
                    console.log("Header placeholder detected, initializing actions...");
                    initializeHeaderActions();
                    observer.disconnect(); // Stop observing once we've initialized
                }
            }
        });
    });
    
    // Start observing
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    // Fallback: try again after a short delay
    setTimeout(function() {
        if ($("#header-actions").length > 0 && $("#header-actions").children().length === 0) {
            console.log("Fallback: Trying to initialize header actions after delay...");
            initializeHeaderActions();
        }
    }, 1000);
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

            // Xóa token ở localStorage
            localStorage.removeItem("access");
            localStorage.removeItem("refresh");

            // Điều hướng về trang đăng nhập
            redirectToLogin();
        },
        error: function (xhr) {
            console.error("Lỗi khi logout:", xhr.responseJSON || xhr.statusText);

            // Dù lỗi vẫn xóa token localStorage và điều hướng
            localStorage.removeItem("access");
            localStorage.removeItem("refresh");

            redirectToLogin();
        }
    });
}

function redirectToLogin() {
    // Determine correct path based on current location
    var currentPath = window.location.pathname;
    var targetPath = "";
    
    if (currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
        currentPath.includes('/admin/') || currentPath.includes('/gacha/')) {
        targetPath = "../user/login.html";
    } else {
        targetPath = "user/login.html";
    }
    window.location.href = targetPath;
}

