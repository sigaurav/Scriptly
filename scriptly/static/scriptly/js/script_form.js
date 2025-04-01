console.log("✅ script_form.js loaded!");

document.addEventListener("DOMContentLoaded", function () {
    console.log("✅ DOM ready");

    // 🔁 Use event delegation so even dynamically added forms are handled
    $(document).on('submit', '.scriptly-job-form', function (e) {
        e.preventDefault();
        console.log("🔥 form submit handler triggered");

        const $form = $(this);
        const formData = new FormData(this);
        const scriptId = $form.data("script-id");

        $('.scriptly-progress').remove();

        const progressHTML = `
            <div class="scriptly-progress">
                <div class="progress">
                    <div class="progress-bar progress-bar-striped active" style="width: 0%" id="progressBar">
                        Submitting Job...
                    </div>
                </div>
            </div>`;
        $form.before(progressHTML);

        $.ajax({
            url: $form.attr('action'),
            type: 'POST',
            data: formData,
            contentType: false,
            processData: false,
            success: function (data) {
                $('.scriptly-progress').remove();
                console.log("✅ AJAX response received", data);

                if (data.valid) {
                    const statusDiv = $(`#form-status-${scriptId}`);
                    statusDiv.html(`<div class="alert alert-success">Job submitted! <a href="${data.redirect}">View Result</a></div>`);

                    const modalHTML = `
                        <div class="modal fade" id="jobCompleteModal" tabindex="-1" role="dialog">
                            <div class="modal-dialog" role="document">
                                <div class="modal-content">
                                    <div class="modal-header bg-success text-white">
                                        <h4 class="modal-title">✅ Job Submitted</h4>
                                    </div>
                                    <div class="modal-body">
                                        <p>${data.message}</p>
                                        <p><strong>Job ID:</strong> ${data.job_id}</p>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
                                    </div>
                                </div>
                            </div>
                        </div>`;
                    $('#jobCompleteModal').remove();
                    $('body').append(modalHTML);
                    $('#jobCompleteModal').modal('show');
                } else {
                    alert("❌ Submission failed.");
                }
            },
            error: function (xhr) {
                $('.scriptly-progress').remove();
                console.error("❌ Server error", xhr.responseText);
                alert("❌ Server error.");
            }
        });
    });

    // 🧪 Optional: Confirm button works
    $(document).on("click", "#Scriptly-form-submit", function (e) {
        e.preventDefault();
        console.log("✅ Submit button clicked!");
        $('.scriptly-job-form').trigger("submit");
    });
});
