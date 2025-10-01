$(document).ready(function () {
    $("input[required]").each(function () {
        $(this).on("blur", function () {
            if ($(this).val().trim() === "") {
                $(this).addClass("input-error");
            }
        });

        $(this).on("input", function () {
            if ($(this).val().trim() !== "") {
                $(this).removeClass("input-error");
            }
        });
    });
});
