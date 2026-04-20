$(document).ready(function() {
    // Check for authentication token
    const token = localStorage.getItem('temple_token');
    if (!token) {
        window.location.href = 'index.html';
        return; // Stop execution if no token
    }

    let players = [];

    // Fetch players for the dropdowns
    $.ajax({
        type: "GET",
        url: "https://syndoria.pythonanywhere.com/api/players/",
        success: function(response) {
            players = response;
            addMatchRow(); // Add the first row once players are loaded
        },
        error: function(xhr) {
            console.error("Failed to fetch players", xhr);
            alert("Error loading player data. Please try again.");
        }
    });

    // Add match row function
    function addMatchRow(roundNum) {
        let options = '<option value="">Select Player</option>';
        players.forEach(p => {
            options += `<option value="${p.id}">${p.name} (Elo: ${parseFloat(p.elo).toFixed(0)})</option>`;
        });

        const rowHtml = `
            <div class="match-row" style="margin-bottom: 15px; display:flex; gap: 10px; align-items:center;">
                <select class="player-a" required>${options}</select>
                <input type="number" class="score-a" placeholder="Wins A" min="0" style="width: 90px;">
                <span>vs</span>
                <input type="number" class="score-b" placeholder="Wins B" min="0" style="width: 90px;">
                <select class="player-b" required>${options}</select>
                <select class="best-of">
                    <option value="1">BO1</option>
                    <option value="3" selected>BO3</option>
                    <option value="5">BO5</option>
                    <option value="7">BO7</option>
                    <option value="9">BO9</option>
                </select>
                <input type="number" class="round" placeholder="Round" value="${roundNum || 1}" min="1" required style="width: 70px;" title="Round">
                <button type="button" class="btn btn-danger remove-match">X</button>
            </div>
        `;
        $('#matches-container').append(rowHtml);
    }

    function getLatestRound() {
        let latestRound = 1;
        $('.match-row').each(function() {
            let r = parseInt($(this).find('.round').val()) || 1;
            if (r > latestRound) {
                latestRound = r;
            }
        });
        return latestRound;
    }

    // Event listeners for adding and removing matches
    $('#btn-add-current-round').click(function() {
        if (players.length > 0) {
            addMatchRow(getLatestRound());
        }
    });

    $('#btn-add-next-round').click(function() {
        if (players.length > 0) {
            addMatchRow(getLatestRound() + 1);
        }
    });

    $(document).on('click', '.remove-match', function() {
        if ($('.match-row').length > 1) {
            $(this).closest('.match-row').remove();
        } else {
            alert('You must have at least one match to submit.');
        }
    });

    // Submit the bulk data
    $('#bulk-report-form').submit(function(e) {
        e.preventDefault();
        
        let matches = [];
        let valid = true;

        $('.match-row').each(function() {
            let pA = $(this).find('.player-a').val();
            let pB = $(this).find('.player-b').val();

            if (pA === pB) {
                alert('A player cannot play against themselves.');
                valid = false;
                return false; // Break loop
            }

            matches.push({
                player_a_id: parseInt(pA),
                player_b_id: parseInt(pB),
                game_wins_a: parseInt($(this).find('.score-a').val() || 0, 10),
                game_wins_b: parseInt($(this).find('.score-b').val() || 0, 10),
                best_of: parseInt($(this).find('.best-of').val()),
                round: parseInt($(this).find('.round').val()) || 1
            });
        });

        if (!valid) return;

        let payload = {
            stage_type: $('#stage-type').val() || 'Round Robin',
            matches: matches
        };

        let tName = $('#tournament-name').val();
        if (tName) {
            payload.tournament_name = tName;
        }

        $.ajax({
            type: "POST",
            url: "https://syndoria.pythonanywhere.com/api/results/bulk/",
            data: JSON.stringify(payload),
            contentType: "application/json",
            success: function(response) {
                alert(response.message || 'Matches created successfully!');
                $('#matches-container').empty();
                addMatchRow(); // Reset with one empty row
            },
            error: function(xhr) {
                let errorMsg = 'Error submitting matches.';
                if (xhr.responseJSON && xhr.responseJSON.error) {
                    errorMsg += '\n' + xhr.responseJSON.error;
                }
                alert(errorMsg);
                console.error(xhr);
            }
        });
    });
});
