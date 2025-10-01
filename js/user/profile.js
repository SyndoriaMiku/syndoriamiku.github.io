$(document).ready(function() {
    // Check if user is logged in
    const token = localStorage.getItem("access");
    if (!token) {
        window.location.href = "/syndoriamiku.github.io/user/login.html";
        return;
    }
    
    try {
        // Decode token to get user info
        const payload = JSON.parse(atob(token.split('.')[1]));
        
        // Get user information from payload
        const username = payload.username;
        const nickname = payload.nickname || username; // Use username if nickname is empty
        const point = payload.point || 0; // Regular points
        const rankingPoint = payload.ranking_point || 0; // Ranking points
        const totalPoints = point + rankingPoint; // Calculate total points
        
        // Display user info
        $("#profile-username").text(username);
        $("#profile-nickname").text(nickname);
        $("#profile-total-points").text(totalPoints);
        
    } catch (error) {
        console.error('Error decoding token:', error);
        showNoticeDialog("Error loading profile information");
        window.location.href = "/syndoriamiku.github.io/user/login.html";
    }
});