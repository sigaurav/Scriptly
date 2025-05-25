document.addEventListener('DOMContentLoaded', function () {
    // ========================
    // Browse Button Handling
    // ========================
    const browseButtons = document.querySelectorAll('.browse-button');

    browseButtons.forEach(button => {
        button.addEventListener('click', function () {
            const inputId = this.getAttribute('data-input-id');
            const inputField = document.getElementById(inputId);
            const inputType = inputField.getAttribute('data-input-type');

            const filePicker = document.createElement('input');
            filePicker.type = 'file';

            if (inputType === 'directory') {
                filePicker.setAttribute('webkitdirectory', '');
                filePicker.setAttribute('directory', '');
            }

            filePicker.style.display = 'none';
            document.body.appendChild(filePicker);

            filePicker.addEventListener('change', function () {
                if (inputType === 'directory') {
                    const files = Array.from(filePicker.files);
                    if (files.length > 0) {
                        const folderPath = files[0].webkitRelativePath.split('/')[0];
                        inputField.value = folderPath;
                    }
                } else {
                    if (filePicker.files.length > 0) {
                        // Only assign if inputField is NOT of type="file"
                        if (inputField.type !== "file") {
                            inputField.value = filePicker.files[0].name;
                        }
                    }
                }
                document.body.removeChild(filePicker);
            });

            filePicker.click();
        });
    });

    // ========================
    // Submit Form Handling (Fixed)
    // ========================
    const forms = document.querySelectorAll('.scriptly-job-form');

    forms.forEach(form => {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            e.stopPropagation(); // ✅ Prevent bubbling to any outer handler

            const submitButton = form.querySelector('button[type="submit"]');
            submitButton.disabled = true;
            const formData = new FormData(form);
            const actionUrl = form.getAttribute('action');

            fetch(actionUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                submitButton.disabled = false;
                if (data.valid && data.redirect) {
                    window.location.href = data.redirect;
                } else {
                    showScriptlyStatusModal('❌ Submission failed. Please check your input or try again.');
                    console.log('Error:', data.errors);
                }
            })
            .catch(error => {
                submitButton.disabled = false;
                showScriptlyStatusModal('❌ Submission failed. Server error.');
                console.error('Error:', error);
            });
        });
    });
