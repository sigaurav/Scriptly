console.log("✅ script_form.js loaded!");

document.addEventListener("DOMContentLoaded", function () {
    console.log("✅ DOM ready");

    // Form submit handler (AJAX submission)
    $(document).on('submit', '.scriptly-job-form', function (e) {
        e.preventDefault();
        console.log("🔥 form submit handler triggered");

        const $form = $(this);
        const formData = new FormData(this);

        $.ajax({
            url: $form.attr('action'),
            type: 'POST',
            data: formData,
            contentType: false,
            processData: false,
            success: function (data) {
                console.log("✅ AJAX response received", data);
                if (data.valid) {
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
                                        <a href="${data.redirect}" class="btn btn-primary">View Result</a>
                                        <button type="button" class="btn btn-default" data-dismiss="modal">Close</button>
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
                console.error("❌ Server error", xhr.responseText);
                alert("❌ Server error.");
            }
        });
    });

    // Browse button logic (delegate to file_browser.js)
    console.log("🟢 Waiting for file_browser.js to handle browse buttons.");
});
