// Case Resubmit – Custom JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // ── Loading overlay on form submit ──────────────────────────────
    const loadingOverlay = document.getElementById('loading-overlay');

    if (loadingOverlay) {
        document.querySelectorAll('form').forEach(function (form) {
            form.addEventListener('submit', function () {
                setTimeout(function () {
                    loadingOverlay.style.display = 'block';
                }, 0);
            });
        });
    }
});
