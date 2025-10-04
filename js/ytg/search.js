$(document).ready(function () {
    // Set current year and month as default
    let thisYear = new Date().getFullYear();
    let thisMonth = new Date().getMonth() + 1;
    $("#year-select").val(thisYear);
    $("#month-select").val(thisMonth);

    // Check for URL parameters and auto-search if present
    const urlParams = new URLSearchParams(window.location.search);
    const username = urlParams.get('username');
    const year = urlParams.get('year');
    const month = urlParams.get('month');
    
    if (username) {
        $("#player-name").val(username);
        if (year) $("#year-select").val(year);
        if (month) $("#month-select").val(month);
        
        // Auto-search when coming from rankings page
        setTimeout(function() {
            searchPlayer();
        }, 500);
    }

    // Search button click event
    $("#search-btn").click(function () {
        searchPlayer();
    });

    // Enter key press in player name input
    $("#player-name").keypress(function (e) {
        if (e.which === 13) { // Enter key pressed
            searchPlayer();
        }
    });
});

/**
 * Search for player ranking data
 */
function searchPlayer() {
    const playerName = $("#player-name").val().trim();
    const year = $("#year-select").val();
    const month = $("#month-select").val();
    
    if (!playerName) {
        showNoticeDialog("Vui lòng nhập tên người chơi!");
        return;
    }
    
    // Hide previous results
    $("#result-card").hide();
    $("#no-results").hide();
    
    showSpinner();
    
    // API call to search for player
    $.ajax({
        type: "GET",
        url: `https://gremory.pythonanywhere.com/api/ranking/user/?username=${encodeURIComponent(playerName)}&year=${year}&month=${month}`,
        success: function (response) {
            hideSpinner();
            
            if (response && response.nickname) {
                // Display player information
                $("#player-nickname").text(response.nickname);
                $("#ranking-points").text(response.ranking_point_earned || 0);
                $("#result-card").fadeIn();
            } else {
                // No results found
                $("#no-results").fadeIn();
            }
        },
        error: function (xhr) {
            hideSpinner();
            
            if (xhr.status === 404) {
                $("#no-results").fadeIn();
            } else {
                showNoticeDialog("Có lỗi xảy ra khi tìm kiếm. Vui lòng thử lại!");
            }
        }
    });
}