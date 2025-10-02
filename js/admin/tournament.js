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

    // Handle add row button
    $(document).on('click', '.add-row-btn', function() {
        addParticipantRow();
    });

    // Handle delete row button
    $(document).on('click', '.delete-row-btn', function() {
        deleteParticipantRow($(this));
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
            // Store users globally for reuse
            window.usersList = response;
            populateUserSelects();
        },
        error: function(error) {
            showNoticeDialog("Failed to load users!");
        }
    });
}

/**
 * Populate all user select dropdowns
 */
function populateUserSelects() {
    $(".user-select").each(function() {
        const select = $(this);
        const currentValue = select.val();
        select.empty();
        select.append(new Option("Select Username", ""));
        
        if (window.usersList) {
            window.usersList.forEach(user => {
                select.append(new Option(user.username, user.id));
            });
        }
        
        if (currentValue) {
            select.val(currentValue);
        }
    });
}

/**
 * Submit tournament result
 */
function submitTournamentResult() {
    const tournamentName = $("#tournament-name").val();
    const results = [];
    
    // Collect all participant data
    $(".participant-row").each(function() {
        const row = $(this);
        const userId = row.find(".user-select").val();
        const position = row.find(".position-select").val();
        const pointEarned = row.find(".point-earned").val();
        const rankingPoint = row.find(".ranking-point").val();
        
        if (userId && position && pointEarned && rankingPoint) {
            // Find username from usersList
            const user = window.usersList.find(u => u.id == userId);
            const username = user ? user.username : "";
            
            results.push({
                username: username,
                position: position,
                point_earned: parseFloat(pointEarned),
                ranking_point_earned: parseFloat(rankingPoint)
            });
        }
    });
    
    if (results.length === 0) {
        showNoticeDialog("Please add at least one participant!");
        return;
    }

    const requestData = {
        tournament_name: tournamentName,
        results: results
    };

    showSpinner();

    $.ajax({
        type: "POST",
        url: "https://gremory.pythonanywhere.com/api/tournament/bulk/",
        headers: {
            "Authorization": "Bearer " + localStorage.getItem("access"),
            "Content-Type": "application/json"
        },
        data: JSON.stringify(requestData),
        success: function(response) {
            hideSpinner();
            showNoticeDialog("Tournament results submitted successfully!");
            // Clear form
            $("#tournament-form")[0].reset();
            // Reset table to single row
            resetParticipantsTable();
        },
        error: function(error) {
            hideSpinner();
            showNoticeDialog("Failed to submit tournament results!");
        }
    });
}

/**
 * Add a new participant row
 */
function addParticipantRow() {
    const newRow = `
        <tr class="participant-row">
            <td>
                <select class="form-control user-select" required>
                    <option value="">Select Username</option>
                </select>
            </td>
            <td>
                <select class="form-control position-select" required>
                    <option value="">Select Position</option>
                    <option value="1">1st Place</option>
                    <option value="2">2nd Place</option>
                    <option value="3">3rd Place</option>
                    <option value="4">4th Place</option>
                    <option value="5">5th Place</option>
                    <option value="6">6th Place</option>
                    <option value="7">7th Place</option>
                    <option value="8">8th Place</option>
                </select>
            </td>
            <td>
                <input type="number" class="form-control point-earned" min="0" step="0.01" required>
            </td>
            <td>
                <input type="number" class="form-control ranking-point" min="0" step="0.01" required>
            </td>
            <td class="table-delete-cell text-center">
                <button type="button" class="icon-as-btn delete-row-btn" title="Delete Row">
                    <img src="/static/cancel.png" alt="Delete" width="16" height="16">
                </button>
            </td>
        </tr>
    `;
    
    // Insert before the add row
    $(".add-row").before(newRow);
    
    // Populate the new user select
    populateUserSelects();
}

/**
 * Delete a participant row
 */
function deleteParticipantRow(button) {
    const rowCount = $(".participant-row").length;
    
    // Prevent deleting the last row
    if (rowCount <= 1) {
        showNoticeDialog("At least one participant row is required!");
        return;
    }
    
    button.closest(".participant-row").remove();
}

/**
 * Reset participants table to single row
 */
function resetParticipantsTable() {
    // Remove all participant rows except the first one
    $(".participant-row:not(:first)").remove();
    
    // Clear the first row
    const firstRow = $(".participant-row:first");
    firstRow.find(".user-select").val("");
    firstRow.find(".position-select").val("");
    firstRow.find(".point-earned").val("");
    firstRow.find(".ranking-point").val("");
}
