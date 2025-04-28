document.addEventListener('DOMContentLoaded', () => {
  console.log("✅ group_card_toggle.js loaded!");

  document.addEventListener('click', function (e) {
    const clickedCard = e.target.closest('.group-card');
    const expandedCard = document.querySelector('.group-card.expanded');
    const clickedCloseBtn = e.target.closest('.close-btn');

    // Close button clicked
    if (clickedCloseBtn) {
      e.preventDefault();
      const card = clickedCloseBtn.closest('.group-card');
      card.classList.remove('expanded');
      clickedCloseBtn.remove();
      return;
    }

    if (!clickedCard) return;  // Click outside any card

    if (clickedCard.classList.contains('expanded')) return;  // Already expanded

    // Collapse previously expanded card
    if (expandedCard) {
      expandedCard.classList.remove('expanded');
      const prevBtn = expandedCard.querySelector('.close-btn');
      if (prevBtn) prevBtn.remove();
    }

    // Expand the clicked card
    clickedCard.classList.add('expanded');

    // Add close button
    const closeBtn = document.createElement('button');
    closeBtn.classList.add('close-btn');
    closeBtn.innerHTML = '&times;';
    clickedCard.appendChild(closeBtn);
  });
});
