$(document).ready(function () {
    //Check admin
    if (!isAdmin()) {
        window.location.href = "/syndoriamiku.github.io/user/login.html";
        return;
    }

    // Load users into select
    loadUsers();

    // Handle form submission
    $("#tournament-form").on("submit", function(e) {
        e.preventDefault();
        submitTournamentResult();
    });

    // Handle cancel button
    $("#cancel-button").click(function() {
        window.location.href = "/syndoriamiku.github.io/admin/";
    });
});

// Listen for nav loaded event
$(document).on('adminNavLoaded', function() {
    //Set activate tournament nav bar
    $("#nav-admin-tournament").addClass("active");
});

/**
 * Check if user is admin by decoding the JWT token and checking is_staff
 * @returns {boolean}
 */
function isAdmin() {
    const token = localStorage.getItem('access');
    if (!token) {
        return false;
    }
    
    try {
        // Get the payload part of the JWT token (second part)
        const payload = token.split('.')[1];
        // Decode the base64 payload
        const decodedPayload = JSON.parse(atob(payload));
        // Check if user is staff
        return decodedPayload.is_staff === true;
    } catch (error) {
        console.error('Error decoding token:', error);
        return false;
    }
}

/**
 * Load users into select
 */
function loadUsers() {
    $.ajax({
        type: "GET",
        url: "https://gremory.pythonanywhere.com/api/users/",
        headers: {
            "Authorization": "Bearer " + localStorage.getItem("access")
        },
        success: function(response) {
            const select = $("#user-select");
            response.forEach(user => {
                select.append(new Option(user.username, user.id));
            });
        },
        error: function(error) {
            showNoticeDialog("Failed to load users!");
        }
    });
}

/**
 * Submit tournament result
 */
function submitTournamentResult() {
    const formData = {
        user: $("#user-select").val(),
        tournament_name: $("#tournament-name").val(),
        place: $("#place-select").val(),
        point_earned: $("#point-earned").val(),
        ranking_point: $("#ranking-point").val()
    };

    showSpinner();

    $.ajax({
        type: "POST",
        url: "https://gremory.pythonanywhere.com/api/tournaments/",
        headers: {
            "Authorization": "Bearer " + localStorage.getItem("access")
        },
        data: formData,
        success: function(response) {
            hideSpinner();
            showNoticeDialog("Tournament result submitted successfully!");
            // Clear form
            $("#tournament-form")[0].reset();
        },
        error: function(error) {
            hideSpinner();
            showNoticeDialog("Failed to submit tournament result!");
        }
    });
}
