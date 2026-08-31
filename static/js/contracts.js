/**
 * NEONDROP CONTRACTS CONTROLLER
 */

document.addEventListener('DOMContentLoaded', () => {
  const contractCards = document.querySelectorAll('.contract-inv-card');
  const countDisplay = document.getElementById('contractSelectedCount');
  const valueDisplay = document.getElementById('contractTotalValue');
  const createBtn = document.getElementById('createContractBtn');
  const rewardModal = document.getElementById('contractRewardModal');

  let selectedItems = new Map();

  contractCards.forEach(card => {
    card.addEventListener('click', () => {
      const id = card.getAttribute('data-id');
      const val = parseFloat(card.getAttribute('data-value'));

      if (selectedItems.has(id)) {
        selectedItems.delete(id);
        card.classList.remove('selected');
      } else {
        if (selectedItems.size >= 10) {
          alert('Максимум 10 предметов для одного контракта.');
          return;
        }
        selectedItems.set(id, val);
        card.classList.add('selected');
      }

      updateContractSummary();
    });
  });

  function updateContractSummary() {
    const count = selectedItems.size;
    let totalVal = 0;
    selectedItems.forEach(v => totalVal += v);

    if (countDisplay) countDisplay.textContent = `${count} / 10`;
    if (valueDisplay) valueDisplay.textContent = `$${totalVal.toFixed(2)}`;

    if (createBtn) {
      if (count >= 3 && count <= 10) {
        createBtn.disabled = false;
        createBtn.textContent = `ПОДПИСАТЬ КОНТРАКТ (${count} ПРЕДМ.)`;
      } else {
        createBtn.disabled = true;
        createBtn.textContent = 'ВЫБЕРИТЕ ОТ 3 ДО 10 ПРЕДМЕТОВ';
      }
    }
  }

  if (createBtn) {
    createBtn.addEventListener('click', async () => {
      const ids = Array.from(selectedItems.keys());
      if (ids.length < 3) return;

      createBtn.disabled = true;
      createBtn.textContent = 'КРАФТИМ СКИН...';

      try {
        const res = await fetch('/contracts/api/create/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
          },
          body: JSON.stringify({ item_ids: ids })
        });

        const data = await res.json();
        if (!data.success) {
          alert(data.error || 'Ошибка создания контракта.');
          createBtn.disabled = false;
          updateContractSummary();
          return;
        }

        window.soundFX.playWin();

        // Show Contract Reward Modal
        const item = data.reward_item;
        document.getElementById('contractWinName').textContent = item.name;
        document.getElementById('contractWinRarity').textContent = item.rarity_name;
        document.getElementById('contractWinRarity').style.color = item.rarity_color;
        document.getElementById('contractWinPrice').textContent = `$${item.value.toFixed(2)}`;
        
        const svgUse = document.getElementById('contractWinSvgUse');
        if (svgUse) {
          svgUse.setAttribute('href', `#icon-${item.image_url || 'generic_weapon'}`);
        }

        if (rewardModal) rewardModal.classList.add('active');

      } catch (e) {
        alert('Ошибка связи с сервером.');
        createBtn.disabled = false;
        updateContractSummary();
      }
    });
  }
});
