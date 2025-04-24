// group_card_toggle.js

document.addEventListener('DOMContentLoaded', () => {

  // Global click listener
  document.addEventListener('click', function (e) {
    const clickedCard = e.target.closest('.group-card');
    const scriptRow = e.target.closest('.script-link');
    const clickedCloseBtn = e.target.closest('.close-btn');
    const expandedCard = document.querySelector('.group-card.expanded');

    // 👉 Clicked on a script row? Load form
    if (scriptRow) {
      e.preventDefault();
      const url = scriptRow.dataset.url;
      const container = scriptRow.closest('.group-card').querySelector('.group-scripts');
      if (!url || !container) return;

      const existingForm = container.querySelector('.script-form-container');
      if (existingForm) existingForm.remove(); // Clean old form

      const scriptList = container.querySelector('.script-table');
      if (scriptList) scriptList.style.display = 'none'; // Hide the table

      const loading = document.createElement('div');
      loading.classList.add('loading');
      loading.innerText = 'Loading form...';
      container.appendChild(loading);

      fetch(url)
        .then(response => response.text())
        .then(html => {
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, 'text/html');
          const form = doc.querySelector('#scriptly-job-form');

          const loadingDiv = container.querySelector('.loading');
          if (loadingDiv) loadingDiv.remove();

          if (form) {
            const formWrapper = document.createElement('div');
            formWrapper.classList.add('script-form-container');

            const backBtn = document.createElement('button');
            backBtn.classList.add('back-to-scripts-btn');
            backBtn.innerHTML = '&larr; Back to Scripts';

            backBtn.addEventListener('click', (e) => {
              e.preventDefault();
              formWrapper.remove();
              if (scriptList) scriptList.style.display = 'table';
            });

            formWrapper.appendChild(backBtn);
            formWrapper.appendChild(form);
            container.appendChild(formWrapper);

// 👇 Reinitialize Scriptly multi-input logic
if (typeof initializeScriptlyScript === 'function') {
  initializeScriptlyScript();
}
          } else {
            container.innerHTML = '<p>Failed to load form.</p>';
          }
        })
        .catch(err => {
          container.innerHTML = '<p>Error loading form.</p>';
          console.error(err);
        });

      return;
    }

    // 👉 Close button clicked
    if (clickedCloseBtn) {
      e.preventDefault();
      const card = clickedCloseBtn.closest('.group-card');
      card.classList.remove('expanded');
      clickedCloseBtn.remove();
      const formContainer = card.querySelector('.script-form-container');
      if (formContainer) formContainer.remove();
      const scriptList = card.querySelector('.script-table');
      if (scriptList) scriptList.style.display = 'table';
      return;
    }

    // 👉 Click outside any card - do nothing
    if (!clickedCard) return;

    // 👉 Click inside already expanded card - do nothing
    if (clickedCard.classList.contains('expanded')) return;

    // 👉 Collapse previously expanded card
    if (expandedCard) {
      expandedCard.classList.remove('expanded');
      const prevBtn = expandedCard.querySelector('.close-btn');
      if (prevBtn) prevBtn.remove();
      const prevForm = expandedCard.querySelector('.script-form-container');
      if (prevForm) prevForm.remove();
      const prevTable = expandedCard.querySelector('.script-table');
      if (prevTable) prevTable.style.display = 'table';
    }

    // 👉 Expand new card
    clickedCard.classList.add('expanded');

    // Add close button
    const closeBtn = document.createElement('button');
    closeBtn.classList.add('close-btn');
    closeBtn.innerHTML = '&times;';
    clickedCard.appendChild(closeBtn);
  });
});
