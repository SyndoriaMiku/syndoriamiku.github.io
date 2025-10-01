$(document).ready(function () {
    // Use relative paths from the current page
    const basePath = window.location.pathname.includes('syndoriamiku.github.io') ? '/syndoriamiku.github.io' : '';
    $("#dialog-placeholder").load(basePath + "/static/dialog_notice.html");
    $("#spinner-placeholder").load(basePath + "/static/spinner.html");
    $("#header-placeholder").load(basePath + "/static/header.html");
});
