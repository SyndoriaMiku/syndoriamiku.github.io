$(document).ready(function() {
    $('#login-form').on('submit', function(e) {
        e.preventDefault();
        
        let username = $('#username').val();
        let password = $('#password').val();
        
        let data = {
            username: username,
            password: password
        };
        
        $.ajax({
            type: "POST",
            url: "https://syndoria.pythonanywhere.com/api/login/",
            data: JSON.stringify(data),
            contentType: "application/json",
            success: function(response) {
                if (response.token) {
                    // Save token to localStorage
                    localStorage.setItem('temple_token', response.token);
                    // Redirect to temple index page
                    window.location.href = 'index.html';
                }
            },
            error: function(xhr) {
                let errorMessage = 'Login failed';
                if (xhr.responseJSON && xhr.responseJSON.error) {
                    errorMessage = xhr.responseJSON.error;
                }
                $('#error-message').text(errorMessage).show();
            }
        });
    });
});