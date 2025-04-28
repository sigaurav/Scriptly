console.log("🟢 file_browser.js loaded!");

document.addEventListener("DOMContentLoaded", function () {
    console.log("✅ DOM ready in file_browser.js");

    const browseButtons = document.querySelectorAll(".browse-btn");
    console.log("🟢 Found browse buttons:", browseButtons.length);

    browseButtons.forEach((button) => {
        button.addEventListener("click", function (e) {
            e.preventDefault();
            const browseType = this.getAttribute("data-type");
            console.log(`🟢 Browse button clicked. Type: ${browseType}`);

            const inputField = this.previousElementSibling;
            console.log("🟢 Target input field:", inputField);

            const fileInput = document.createElement('input');
            fileInput.style.display = 'none';

            if (browseType === 'directory') {
                fileInput.setAttribute('type', 'file');
                fileInput.setAttribute('webkitdirectory', '');
                fileInput.setAttribute('directory', '');
                fileInput.setAttribute('multiple', '');
            } else {
                fileInput.setAttribute('type', 'file');
            }

            fileInput.addEventListener('change', function (event) {
                if (browseType === 'directory' && event.target.files.length > 0) {
                    const relativePath = event.target.files[0].webkitRelativePath;
                    const directoryPath = relativePath.split('/')[0];
                    inputField.value = directoryPath;
                    console.log(`📂 Directory selected: ${directoryPath}`);
                } else if (event.target.files.length > 0) {
                    const fileName = event.target.files[0].name;
                    inputField.value = fileName;
                    console.log(`📄 File selected: ${fileName}`);
                }
            });

            document.body.appendChild(fileInput);
            fileInput.click();
            document.body.removeChild(fileInput);
        });
    });
});
