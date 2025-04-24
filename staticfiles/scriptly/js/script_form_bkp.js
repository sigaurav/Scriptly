console.log("✅ script_form.js loaded!");

document.addEventListener("DOMContentLoaded", function () {
    console.log("✅ DOM ready");

    // Safely unbind and bind the submit handler
    $(document).off('submit', '.script-form').on('submit', '.script-form', function (e) {
        e.preventDefault();  // Prevent the default form submission (this will stop the page from navigating away)
        console.log("📤 Intercepted form submit");

        const $form = $(this);
        const formData = new FormData(this);

        // Remove any existing progress bar
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
                console.log("DEBUG: Received response", data);  // Log the response

                if (data.valid) {
                    console.log("✅ Job successfully submitted");

                    // Modal to show the status
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

                    // Start polling job status
                    if (data.job_id) {
                        pollJobStatus(data.job_id);  // Pass the correct job_id here
                    } else {
                        console.error("❌ Job ID is missing in the response.");
                    }
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

    // Make sure the submit button is correctly handled, no default form submit
    $("#Scriptly-form-submit").on("click", function (e) {
        e.preventDefault();  // Prevent default button action (this stops redirect)
        console.log("✅ Submit button clicked!");
        $('.script-form').submit();  // Trigger form submit manually via AJAX
    });
});

function pollJobStatus(jobId) {
    console.log(`📡 Polling job status for jobId: ${jobId}`);

    $.ajax({
        url: '/scripts/jobs/results/status/' + jobId,  // Adjusted to your server endpoint for job status
        success: function(data) {
            console.log("DEBUG: Job status data", data);  // Log job status data
            if (data.status === 'success') {
                // Job completed, show completion message
                $('#jobCompleteModal').modal('show');
                clearInterval(pollInterval);  // Stop polling when job is done
            } else if (data.status === 'started') {
                // Update progress bar during execution
                $('.progress-bar').css('width', data.progress + '%').text(`Processing: ${data.progress}%`);
            } else if (data.status === 'failure') {
                // Handle job failure
                alert('Job failed: ' + data.error);
                clearInterval(pollInterval);
            }
        }
    });
}

// Start polling for job status
var pollInterval;
function startPolling(jobId) {
    pollInterval = setInterval(function() {
        pollJobStatus(jobId); // Poll job status every 3 seconds
    }, 3000);
}
