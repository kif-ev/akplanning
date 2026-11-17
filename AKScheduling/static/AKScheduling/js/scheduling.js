/**
 * Escape text for safely inserting it into HTML (e.g., free text entered by users)
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Create HTML showing who resolved a constraint violation manually and why (empty if not resolved manually)
 */
function cvResolutionHtml(cv) {
    if (!cv.resolution_display)
        return '';
    return "<div class='small fst-italic'>" + escapeHtml(cv.resolution_display) + "</div>";
}

function loadCVs(url, callback_success, callback_error) {
    $.ajax({
        url: url,
        type: 'GET',
        success: callback_success,
        error: callback_error
    });
}

const default_cv_callback_error = function (response) {
    alert("{% trans 'Cannot load current violations from server' %}");
}
