/**
 * NEONDROP CS:GO ROULETTE CONTROLLER
 * Precise server-aligned spinning tape, realistic physics & sound ticks
 */

document.addEventListener('DOMContentLoaded', () => {
  const openCaseBtn = document.getElementById('openCaseBtn');
  const rouletteContainer = document.getElementById('rouletteContainer');
  const rouletteTrack = document.getElementById('rouletteTrack');
  const rouletteViewport = document.getElementById('rouletteViewport');
  const rouletteStatusBar = document.getElementById('rouletteStatusBar');
  const winModal = document.getElementById('winModal');
  const caseSlug = openCaseBtn ? openCaseBtn.getAttribute('data-case-slug') : null;

  if (!openCaseBtn || !caseSlug) return;

  let isOpening = false;
  let lastWonItem = null;
  let lastInvId = null;

  openCaseBtn.addEventListener('click', async () => {
    if (isOpening) return;
    isOpening = true;

    openCaseBtn.disabled = true;
    openCaseBtn.classList.add('loading');
    openCaseBtn.innerHTML = '<span>ОТКРЫВАЕМ...</span>';
    rouletteContainer.style.display = 'block';
    rouletteStatusBar.style.display = 'block';

    // Scroll smoothly to roulette
    rouletteContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });

    try {
      const response = await fetch(`/cases/${caseSlug}/open/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: new URLSearchParams({
          'client_seed': Math.random().toString(36).substring(2, 15)
        })
      });

      const data = await response.json();

      if (!data.success) {
        alert(data.error || 'Ошибка при открытии кейса');
        resetOpenButton();
        return;
      }

      // Update Live Balance
      window.updateUserBalance(data.new_balance);

      lastWonItem = data.won_item;
      lastInvId = data.inventory_id;

      // Populate Track Items
      buildRouletteTrack(data.tape, data.winning_index);

      // Start Spin Animation
      setTimeout(() => {
        spinRoulette(data.winning_index, data.won_item);
      }, 100);

    } catch (err) {
      console.error(err);
      alert('Произошла ошибка соединения с сервером.');
      resetOpenButton();
    }
  });

  function buildRouletteTrack(tape, winningIndex) {
    rouletteTrack.style.transition = 'none';
    rouletteTrack.style.transform = 'translateX(0px)';
    rouletteTrack.innerHTML = '';

    tape.forEach((item, index) => {
      const card = document.createElement('div');
      card.className = 'roulette-item';
      card.style.setProperty('--r-color', item.rarity_color);
      card.setAttribute('data-index', index);

      card.innerHTML = `
        <div class="roulette-item-weapon">${item.weapon_type}</div>
        <div class="roulette-item-img-box">
          <svg class="roulette-item-img"><use href="#icon-${item.image_url || 'generic_weapon'}"></use></svg>
        </div>
        <div class="roulette-item-skin">${item.skin_name}</div>
        <div class="roulette-item-price">$${item.value.toFixed(2)}</div>
      `;
      rouletteTrack.appendChild(card);
    });
  }

  function spinRoulette(winningIndex, wonItem) {
    const cardEl = rouletteTrack.children[0];
    const cardStyle = window.getComputedStyle(cardEl);
    const cardWidth = cardEl.offsetWidth;
    const cardMargin = parseFloat(cardStyle.marginLeft) + parseFloat(cardStyle.marginRight);
    const totalCardWidth = cardWidth + cardMargin;

    const viewportWidth = rouletteViewport.offsetWidth;
    
    // Slight random offset inside the card (+- 35% of card width) for realistic variation
    const jitter = (Math.random() - 0.5) * (cardWidth * 0.7);

    // Target landing point: center the winning card under the needle
    const targetOffset = (winningIndex * totalCardWidth) + (totalCardWidth / 2) - (viewportWidth / 2) + jitter;

    // Trigger tick sound loop
    let tickCount = 0;
    const tickInterval = setInterval(() => {
      if (tickCount < 40) {
        window.soundFX.playTick();
        tickCount++;
      } else {
        clearInterval(tickInterval);
      }
    }, 120);

    // 6 seconds cubic-bezier deceleration
    rouletteTrack.style.transition = 'transform 6s cubic-bezier(0.12, 0.8, 0.33, 1)';
    rouletteTrack.style.transform = `translateX(-${targetOffset}px)`;

    setTimeout(() => {
      clearInterval(tickInterval);
      window.soundFX.playWin();

      // Highlight winning card
      const winningCard = rouletteTrack.children[winningIndex];
      if (winningCard) {
        winningCard.classList.add('winner-landed');
      }

      // Show Reveal Modal
      setTimeout(() => {
        showWinModal(wonItem, lastInvId);
        resetOpenButton();
      }, 800);

    }, 6100);
  }

  function showWinModal(item, invId) {
    document.getElementById('winItemWeapon').textContent = item.weapon_type;
    document.getElementById('winItemSkin').textContent = item.skin_name;
    document.getElementById('winItemRarity').textContent = item.rarity_name;
    document.getElementById('winItemRarity').style.color = item.rarity_color;
    document.getElementById('winItemPrice').textContent = `$${item.value.toFixed(2)}`;
    
    const winSvgUse = document.getElementById('winItemSvgUse');
    if (winSvgUse) {
      winSvgUse.setAttribute('href', `#icon-${item.image_url || 'generic_weapon'}`);
    }

    const modalWinCard = document.querySelector('.modal-win-card');
    if (modalWinCard) {
      modalWinCard.style.setProperty('--win-rarity-color', item.rarity_color);
    }

    const sellBtn = document.getElementById('modalSellBtn');
    sellBtn.textContent = `ПРОДАТЬ ЗА $${item.value.toFixed(2)}`;
    sellBtn.onclick = () => sellWonItem(invId);

    winModal.classList.add('active');
  }

  async function sellWonItem(invId) {
    if (!invId) return;
    try {
      const res = await fetch(`/inventory/sell/${invId}/`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCookie('csrftoken')
        }
      });
      const data = await res.json();
      if (data.success) {
        window.updateUserBalance(data.new_balance);
        winModal.classList.remove('active');
      } else {
        alert(data.error);
      }
    } catch (e) {
      alert('Ошибка при продаже.');
    }
  }

  function resetOpenButton() {
    isOpening = false;
    openCaseBtn.disabled = false;
    openCaseBtn.classList.remove('loading');
    openCaseBtn.innerHTML = '<span>ОТКРЫТЬ КЕЙС</span>';
  }

  // Close modal button
  const closeWinModalBtn = document.getElementById('closeWinModalBtn');
  if (closeWinModalBtn) {
    closeWinModalBtn.addEventListener('click', () => {
      winModal.classList.remove('active');
    });
  }
});
