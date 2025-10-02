$(document).ready(function () {
    
// Get roll counts
    $("#roll_button").click(function() {
        let rolls = parseInt($("#roll_count").val());
        if (isNaN(rolls) || rolls < 1) {
            alert("Vui lòng nhập số lần quay hợp lệ.");
            return;
        }
        
        $.ajax({
            type: "POST",
            url: "" // TODO: Add your API endpoint here
        });
    });

});