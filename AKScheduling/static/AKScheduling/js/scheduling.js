function loadCVs(url, callback_success, callback_error) {
    $.ajax({
        url: url,
        type: 'GET',
        success: callback_success,
        error: callback_error
    });
}

const default_cv_callback_error = function(response) {
   alert("{% trans 'Cannot load current violations from server' %}");
}
