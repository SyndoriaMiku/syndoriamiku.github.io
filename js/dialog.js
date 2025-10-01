/* Notice Dialog */
function showNoticeDialog(message) {
    $("#dialog-message").text(message);
    $("#notice-dialog-overlay").fadeIn(200);
}

/* Close Notice Dialog */
function closeNoticeDialog() {
    $("#notice-dialog-overlay").fadeOut(200);
}

/* Close Notice Dialog on click */
$(document).on("click", "#dialog-close", function () {
    closeNoticeDialog();
});
