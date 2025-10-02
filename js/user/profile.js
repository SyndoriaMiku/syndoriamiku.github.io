$(document).ready(function() {
    // Check if user is logged in
    const token = localStorage.getItem("access");
    if (!token) {
        window.location.href = "/user/login.html";
        return;
    }
    
    try {
        // Get all user info from API
        $.ajax({
            type: "GET",
            url: "https://gremory.pythonanywhere.com/api/user/",
            headers: {
                "Authorization": "Bearer " + token
            },
            success: function(response) {
                // Get the payload part of the JWT token (second part)
                $("#profile-username").text(response.username);
                $("#profile-nickname").text(response.nickname || response.username);
                $("#profile-total-points").text(response.point_balance || "0");
                $("#profile-monthly-points").text(response.this_month_ranking_points || "0");
            }
        });
    } catch (error) {
        showNoticeDialog("Error loading profile data!");
        window.location.href = "/";
    }
});