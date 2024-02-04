$(document).ready(function () {

    loadData("0");

    //Add player button
    $("#btn-add-player").click(function () {
        //Show dialog
        on("#player-dialog");

        //Clear input
        $("#player-id-input").val("");
        $("#player-name-input").val("");

        //Automatic ID
        $.ajax({
            type: "GET",
            url: "https://syndoria.pythonanywhere.com/api/new/",
            success: function (response) {
                $("#player-id-input").val(response.id);
            }
        });

        //Focus on name input
        $("#player-name-input").focus();
    });

    //Cancel player dialog
    $("#btn-cancel-add").click(function () {
        off("#player-dialog");
    });

    //Sort table
    $(".sort").click(function () {
        var table = $(this).parents("table").eq(0);
        var rows = table.find("tr:gt(0)").toArray().sort(comparer($(this).index()));
        this.asc = !this.asc;
        if (!this.asc){rows = rows.reverse()}
        for (var i=0; i<rows.length; i++) {table.append(rows[i])}
    });

    //Report result button
    $("#result").click(function() {
        //Show dialog
        on("#result-dialog");

        $("#player-1").val("0");
        $("#player-2").val("0");

        //Get player list

        $.ajax({
            type: "GET",
            url: "https://syndoria.pythonanywhere.com/api/players/",
            success: function (response) {
                for (let i=0; i<response.length; i++) {
                    let playerId = response[i].id;
                    let playerName = response[i].name;

                    //Build HTML
                    var option = $(`<option value="${playerId}">${playerName}</option>`);

                    //Append HTML to table
                    $("#player-1").append(option.clone());
                    $("#player-2").append(option.clone());
                }
            }
        });
    })

    //Cancel result dialog
    $("#btn-close-result").click(function () {
        off("#result-dialog");
        $("#player-1").empty().append('<option value="0">Chọn người chơi</option>');
        $("#player-2").empty().append('<option value="0">Chọn người chơi</option>');
    });

    //Add player button
    $("#btn-save-player").click(function () {
        //Get data
        let playerId = parseInt($("#player-id-input").val());
        let playerName = $("#player-name-input").val();
        let playerElo = "500.0";

        //Build JSON
        let data = {
            "id": playerId,
            "name": playerName,
            "elo": playerElo
        };

        //Post data
        $.ajax({
            type: "POST",
            url: "https://syndoria.pythonanywhere.com/api/players/",
            data: JSON.stringify(data),
            dataType: "json",
            contentType: "application/json",
            success: function (response) {
                //Close dialog
                off("#player-dialog");

                //Reload table
                loadData("0");
            }
        });

    });


    //Report Player 1 Win
    $("#btn-p1").click(function () {
        //Get data
        let player1Id = $("#player-1").val();
        let player2Id = $("#player-2").val();

        // Build JSON
        let data = {
            "winner": player1Id,
            "loser": player2Id
        };

        //Post data
        $.ajax({
            type: "POST",
            url: "https://syndoria.pythonanywhere.com/api/result/",
            data: JSON.stringify(data),
            dataType: "json",
            contentType: "application/json",
            success: function (response) {
                //Close dialog
                off("#result-dialog");

                //Reload table
                loadData("0");
            }
        });

        $("#player-1").empty().append('<option value="0">Chọn người chơi</option>');
        $("#player-2").empty().append('<option value="0">Chọn người chơi</option>');
    });

    //Report Player 2 Win
    $("#btn-p2").click(function () {
        //Get data
        let player1Id = $("#player-1").val();
        let player2Id = $("#player-2").val();

        // Build JSON
        let data = {
            "winner": player2Id,
            "loser": player1Id
        };

        //Post data
        $.ajax({
            type: "POST",
            url: "https://syndoria.pythonanywhere.com/api/result/",
            data: JSON.stringify(data),
            dataType: "json",
            contentType: "application/json",
            success: function (response) {
                //Close dialog
                off("#result-dialog");

                //Reload table
                loadData("0");
            }
        });

        $("#player-1").empty().append('<option value="0">Chọn người chơi</option>');
        $("#player-2").empty().append('<option value="0">Chọn người chơi</option>');
    });












});























function on(target) {
    $(target).show();
}

function off(target) {
    $(target).hide();
}



function loadData(query) {
    $("#player-table tbody").empty();
    $.ajax({
        type: "GET",
        url: `https://syndoria.pythonanywhere.com/api/players/?query=${query}`,
        success: function (response) {
            for (let i=0; i<response.length; i++) {
                let playerId = response[i].id;
                let playerName = response[i].name;
                let playerElo = response[i].elo;
                //Build HTML
                var row = $(`<tr class="player-row">
                <td class="text-left">${playerId}</td>
                <td class="text-left">${playerName}</td>
                <td class="text-left">${playerElo}</td>
                </tr>`);
                //Append HTML to table
                $("#player-table tbody").append(row);
            }
        }
    })

}

/**-------------------------
 * Comparer for table sort
 * Author: Internet (21/07/2023)
 */

function comparer (input) {
    return function(a, b) {
        var valA = getValue(a, input), valB = getValue(b, input)
        return $.isNumeric(valA) && $.isNumeric(valB) ? valA - valB : valA.toString().localeCompare(valB)
    }
}

/**-------------------------
 * Get value of table row
 * Author: NVHa (21/07/2023)
 */

function getValue (row, input) {
    return $(row).children("td").eq(input).text();
}
