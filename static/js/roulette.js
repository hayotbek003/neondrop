/**
 * NEONDROP CS:GO STYLE MULTI-ROULETTE (1-5) & SOUND ENGINE
 * Precise server-aligned tapes, synchronized multi-track physics, instant skip, and batch selling
 */

class RouletteSoundManager {
  constructor() {
    this.isMuted = localStorage.getItem('neondrop_sound_muted') === 'true';
    this.volume = parseFloat(localStorage.getItem('neondrop_sound_volume'));
    if (isNaN(this.volume) || this.volume < 0 || this.volume > 1) {
      this.volume = 0.8;
    }

    this.audioCtx = null;
    this.gainNode = null;
    this.hasAudioUnlocked = false;

    // Audio elements
    this.startAudio = this.createAudioElement('/static/sounds/roulette_start.mp3');
    this.winAudio = this.createAudioElement('/static/sounds/roulette_win.mp3');
    
    // Pool of tick audio elements for rapid non-overlapping playback
    this.tickPoolSize = 6;
    this.tickPool = [];
    this.tickPoolIndex = 0;
    for (let i = 0; i < this.tickPoolSize; i++) {
      this.tickPool.push(this.createAudioElement('/static/sounds/roulette_tick.mp3'));
    }

    this.initUI();
  }

  createAudioElement(src) {
    try {
      const audio = new Audio(src);
      audio.preload = 'auto';
      audio.volume = this.isMuted ? 0 : this.volume;
      return audio;
    } catch (e) {
      return null;
    }
  }

  initAudioContext() {
    if (!this.audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        this.audioCtx = new AudioContextClass();
        this.gainNode = this.audioCtx.createGain();
        this.gainNode.gain.setValueAtTime(this.isMuted ? 0 : this.volume, this.audioCtx.currentTime);
        this.gainNode.connect(this.audioCtx.destination);
      }
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
    this.hasAudioUnlocked = true;
  }

  setVolume(newVolume) {
    this.volume = Math.max(0, Math.min(1, newVolume));
    localStorage.setItem('neondrop_sound_volume', this.volume.toString());

    const effectiveVol = this.isMuted ? 0 : this.volume;

    if (this.startAudio) this.startAudio.volume = effectiveVol;
    if (this.winAudio) this.winAudio.volume = effectiveVol;
    this.tickPool.forEach(a => { if (a) a.volume = effectiveVol; });

    if (this.gainNode && this.audioCtx) {
      this.gainNode.gain.setValueAtTime(effectiveVol, this.audioCtx.currentTime);
    }

    this.updateUI();
  }

  setMuted(muted) {
    this.isMuted = !!muted;
    localStorage.setItem('neondrop_sound_muted', this.isMuted.toString());
    this.setVolume(this.volume);
  }

  toggleMute() {
    this.setMuted(!this.isMuted);
  }

  initUI() {
    const soundToggleBtn = document.getElementById('soundToggleBtn');
    const volumeSlider = document.getElementById('volumeSlider');

    if (soundToggleBtn) {
      soundToggleBtn.addEventListener('click', () => {
        this.initAudioContext();
        this.toggleMute();
      });
    }

    if (volumeSlider) {
      volumeSlider.value = Math.round(this.volume * 100);
      volumeSlider.addEventListener('input', (e) => {
        this.initAudioContext();
        if (this.isMuted) this.isMuted = false;
        this.setVolume(parseInt(e.target.value, 10) / 100);
      });
    }

    this.updateUI();
  }

  updateUI() {
    const soundIcon = document.getElementById('soundIcon');
    const soundLabel = document.getElementById('soundLabel');
    const soundToggleBtn = document.getElementById('soundToggleBtn');
    const volumeSlider = document.getElementById('volumeSlider');
    const volumePercent = document.getElementById('volumePercent');

    const pct = Math.round(this.volume * 100);

    if (volumeSlider) volumeSlider.value = pct;
    if (volumePercent) volumePercent.textContent = `${pct}%`;

    if (this.isMuted || this.volume === 0) {
      if (soundIcon) soundIcon.textContent = '🔇';
      if (soundLabel) soundLabel.textContent = 'Выкл.';
      if (soundToggleBtn) soundToggleBtn.classList.add('muted');
    } else {
      if (soundIcon) soundIcon.textContent = pct > 50 ? '🔊' : '🔉';
      if (soundLabel) soundLabel.textContent = 'Звук';
      if (soundToggleBtn) soundToggleBtn.classList.remove('muted');
    }
  }

  playStart() {
    if (this.isMuted) return;
    this.initAudioContext();

    if (this.startAudio) {
      this.startAudio.currentTime = 0;
      this.startAudio.play().catch(() => this.synthStart());
    } else {
      this.synthStart();
    }
  }

  playTick() {
    if (this.isMuted) return;
    this.initAudioContext();

    const audio = this.tickPool[this.tickPoolIndex];
    this.tickPoolIndex = (this.tickPoolIndex + 1) % this.tickPoolSize;

    if (audio) {
      audio.currentTime = 0;
      audio.play().catch(() => this.synthTick());
    } else {
      this.synthTick();
    }
  }

  playWin() {
    if (this.isMuted) return;
    this.initAudioContext();

    if (this.winAudio) {
      this.winAudio.currentTime = 0;
      this.winAudio.play().catch(() => this.synthWin());
    } else {
      this.synthWin();
    }
  }

  synthTick() {
    try {
      if (!this.audioCtx || !this.gainNode) return;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc.type = 'triangle';
      osc.frequency.setValueAtTime(1900, this.audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(120, this.audioCtx.currentTime + 0.035);

      gain.gain.setValueAtTime(0.3 * (this.isMuted ? 0 : this.volume), this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.035);

      osc.connect(gain);
      gain.connect(this.gainNode);

      osc.start();
      osc.stop(this.audioCtx.currentTime + 0.035);
    } catch (e) {}
  }

  synthStart() {
    try {
      if (!this.audioCtx || !this.gainNode) return;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(140, this.audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(650, this.audioCtx.currentTime + 0.6);

      gain.gain.setValueAtTime(0.25 * (this.isMuted ? 0 : this.volume), this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.65);

      osc.connect(gain);
      gain.connect(this.gainNode);

      osc.start();
      osc.stop(this.audioCtx.currentTime + 0.65);
    } catch (e) {}
  }

  synthWin() {
    try {
      if (!this.audioCtx || !this.gainNode) return;
      const chords = [523.25, 659.25, 783.99, 1046.50];
      chords.forEach((freq, i) => {
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();

        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime + i * 0.09);

        gain.gain.setValueAtTime(0.22 * (this.isMuted ? 0 : this.volume), this.audioCtx.currentTime + i * 0.09);
        gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + i * 0.09 + 0.7);

        osc.connect(gain);
        gain.connect(this.gainNode);

        osc.start(this.audioCtx.currentTime + i * 0.09);
        osc.stop(this.audioCtx.currentTime + i * 0.09 + 0.7);
      });
    } catch (e) {}
  }
}

// ==================== MULTI-ROULETTE CONTROLLER ====================
document.addEventListener('DOMContentLoaded', () => {
  const openCaseBtn = document.getElementById('openCaseBtn');
  const multiRouletteContainer = document.getElementById('multiRouletteContainer');
  const rouletteTracksWrapper = document.getElementById('rouletteTracksWrapper');
  const skipAnimationBtn = document.getElementById('skipAnimationBtn');
  const winModal = document.getElementById('winModal');
  const caseUnitPriceEl = document.getElementById('caseUnitPrice');

  if (!openCaseBtn || !caseUnitPriceEl) return;

  const caseSlug = openCaseBtn.getAttribute('data-case-slug');
  const unitPrice = parseFloat(caseUnitPriceEl.getAttribute('data-price')) || 0.0;
  let freeOpeningsAvailable = parseInt(openCaseBtn.getAttribute('data-free-openings')) || 0;

  const soundManager = new RouletteSoundManager();

  let selectedQuantity = 1;
  let isOpening = false;
  let activeAnimationId = null;
  let isSkipped = false;
  let currentResults = [];

  // ==================== QUANTITY SELECTOR ====================
  const qtyPresets = document.querySelectorAll('.btn-qty-preset');
  const qtyDisplay = document.getElementById('qtyDisplay');
  const qtyMinusBtn = document.getElementById('qtyMinusBtn');
  const qtyPlusBtn = document.getElementById('qtyPlusBtn');
  const caseCalcSummary = document.getElementById('caseCalcSummary');
  const openBtnText = document.getElementById('openBtnText');

  function updateQuantity(newQty) {
    selectedQuantity = Math.max(1, Math.min(5, newQty));
    if (qtyDisplay) qtyDisplay.textContent = selectedQuantity;

    qtyPresets.forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.getAttribute('data-qty')) === selectedQuantity);
    });

    if (rouletteTracksWrapper) {
      rouletteTracksWrapper.setAttribute('data-qty', selectedQuantity.toString());
    }

    const paidQuantity = Math.max(0, selectedQuantity - freeOpeningsAvailable);
    const totalCost = paidQuantity * unitPrice;

    if (caseCalcSummary) {
      if (freeOpeningsAvailable >= selectedQuantity) {
        caseCalcSummary.innerHTML = `<span>Количество: ${selectedQuantity}</span> &bull; <span>Оплата: <strong class="text-green">БЕСПЛАТНО (${selectedQuantity} шт.)</strong></span>`;
      } else if (freeOpeningsAvailable > 0) {
        caseCalcSummary.innerHTML = `<span>Бесплатно: ${freeOpeningsAvailable} шт. &bull; К оплате: ${paidQuantity} × $${unitPrice.toFixed(2)}</span> &bull; <span>Итого: <strong class="text-cyan">$${totalCost.toFixed(2)}</strong></span>`;
      } else {
        caseCalcSummary.innerHTML = `<span>1 кейс = $${unitPrice.toFixed(2)} &bull; ${selectedQuantity} шт.</span> &bull; <span>Итого: <strong class="text-cyan">$${totalCost.toFixed(2)}</strong></span>`;
      }
    }

    if (openBtnText) {
      if (paidQuantity === 0) {
        openBtnText.textContent = `ОТКРЫТЬ БЕСПЛАТНО (×${selectedQuantity})`;
      } else {
        openBtnText.textContent = `ОТКРЫТЬ ×${selectedQuantity} ($${totalCost.toFixed(2)})`;
      }
    }
  }

  qtyPresets.forEach(btn => {
    btn.addEventListener('click', () => {
      updateQuantity(parseInt(btn.getAttribute('data-qty'), 10));
    });
  });

  if (qtyMinusBtn) {
    qtyMinusBtn.addEventListener('click', () => updateQuantity(selectedQuantity - 1));
  }
  if (qtyPlusBtn) {
    qtyPlusBtn.addEventListener('click', () => updateQuantity(selectedQuantity + 1));
  }

  updateQuantity(1);

  // ==================== OPEN CASE EVENT ====================
  openCaseBtn.addEventListener('click', async () => {
    if (isOpening) return;
    isOpening = true;
    isSkipped = false;

    soundManager.initAudioContext();

    openCaseBtn.disabled = true;
    openCaseBtn.classList.add('loading');
    openBtnText.textContent = 'ОТКРЫВАЕМ...';

    multiRouletteContainer.style.display = 'block';
    multiRouletteContainer.classList.remove('winner-active');
    multiRouletteContainer.classList.add('spinning');
    if (skipAnimationBtn) skipAnimationBtn.style.display = 'inline-block';

    multiRouletteContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });

    try {
      // 1. Django Backend Authoritative Result
      const response = await fetch(`/cases/${caseSlug}/open/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': typeof getCsrfToken === 'function' ? getCsrfToken() : (getCookie('csrftoken') || '')
        },
        credentials: 'same-origin',
        body: new URLSearchParams({
          'quantity': selectedQuantity.toString(),
          'client_seed': Math.random().toString(36).substring(2, 15)
        })
      });

      const data = await response.json();

      if (!data.success) {
        alert(data.error || 'Ошибка при открытии кейса');
        resetOpenButton();
        return;
      }

      // Update Live Balance across header
      window.updateUserBalance(data.new_balance);

      freeOpeningsAvailable = data.free_openings_remaining || 0;
      openCaseBtn.setAttribute('data-free-openings', freeOpeningsAvailable.toString());

      currentResults = data.results || [data];

      // 2. Build Multi-Roulette Lanes
      buildMultiRouletteLanes(currentResults);

      // 3. Play Start Sound
      soundManager.playStart();

      // 4. Start Physics Animation on all tracks
      setTimeout(() => {
        spinMultiRoulettePhysics(currentResults);
      }, 80);

    } catch (err) {
      console.error(err);
      alert('Произошла ошибка соединения с сервером.');
      resetOpenButton();
    }
  });

  // ==================== SKIP ANIMATION ====================
  if (skipAnimationBtn) {
    skipAnimationBtn.addEventListener('click', () => {
      if (!isOpening || isSkipped) return;
      isSkipped = true;
      if (activeAnimationId) cancelAnimationFrame(activeAnimationId);

      // Instantly position all tracks to winning targets
      const lanes = rouletteTracksWrapper.querySelectorAll('.roulette-lane');
      lanes.forEach((lane) => {
        const track = lane.querySelector('.roulette-track');
        const targetOffset = parseFloat(lane.getAttribute('data-target-offset')) || 0;
        track.style.transition = 'none';
        track.style.transform = `translate3d(-${targetOffset}px, 0, 0)`;

        const winningIndex = parseInt(lane.getAttribute('data-winning-index'), 10) || 50;
        const winCard = track.children[winningIndex];
        if (winCard) winCard.classList.add('winner-landed');
      });

      onMultiRouletteStopped(currentResults);
    });
  }

  // ==================== BUILD MULTI LANES ====================
  function buildMultiRouletteLanes(results) {
    rouletteTracksWrapper.innerHTML = '';
    rouletteTracksWrapper.setAttribute('data-qty', results.length.toString());

    results.forEach((res, laneIndex) => {
      const lane = document.createElement('div');
      lane.className = 'roulette-lane';
      lane.id = `rouletteLane_${laneIndex}`;
      lane.setAttribute('data-winning-index', res.winning_index);

      lane.innerHTML = `
        <div class="roulette-needle"></div>
        <div class="roulette-viewport">
          <div class="roulette-track"></div>
        </div>
      `;

      const track = lane.querySelector('.roulette-track');
      res.tape.forEach((item, itemIdx) => {
        const card = document.createElement('div');
        card.className = 'roulette-item';
        card.style.setProperty('--r-color', item.rarity_color);
        card.setAttribute('data-index', itemIdx);

        card.innerHTML = `
          <div class="roulette-item-weapon">${item.weapon_type}</div>
          <div class="roulette-item-img-box">
            <svg class="roulette-item-img"><use href="#icon-${item.image_url || 'generic_weapon'}"></use></svg>
          </div>
          <div class="roulette-item-skin">${item.skin_name}</div>
          <div class="roulette-item-price">$${item.value.toFixed(2)}</div>
        `;
        track.appendChild(card);
      });

      rouletteTracksWrapper.appendChild(lane);
    });
  }

  // ==================== PHYSICS MULTI SPIN ====================
  function spinMultiRoulettePhysics(results) {
    const lanes = rouletteTracksWrapper.querySelectorAll('.roulette-lane');
    if (!lanes.length) return;

    const firstLane = lanes[0];
    const track = firstLane.querySelector('.roulette-track');
    const firstCard = track.children[0];
    if (!firstCard) return;

    const cardStyle = window.getComputedStyle(firstCard);
    const cardWidth = firstCard.offsetWidth;
    const cardMargin = parseFloat(cardStyle.marginLeft) + parseFloat(cardStyle.marginRight);
    const totalCardWidth = cardWidth + cardMargin;
    const viewportWidth = firstLane.querySelector('.roulette-viewport').offsetWidth;

    // Calculate landing offsets for each lane with individual micro-jitter
    const laneConfigs = [];
    lanes.forEach((lane) => {
      const winningIndex = parseInt(lane.getAttribute('data-winning-index'), 10) || 50;
      const jitter = (Math.random() - 0.5) * (cardWidth * 0.5);
      const targetOffset = (winningIndex * totalCardWidth) + (totalCardWidth / 2) - (viewportWidth / 2) + jitter;
      lane.setAttribute('data-target-offset', targetOffset.toString());
      laneConfigs.push({
        lane: lane,
        track: lane.querySelector('.roulette-track'),
        targetOffset: targetOffset,
        winningIndex: winningIndex,
      });
    });

    const totalDuration = 6200 + (Math.random() * 200 - 100);
    const startTime = performance.now();
    let lastPassedIndex = -1;

    // Easing curve: Fast start, long spin, smooth deceleration with gentle settle
    function customEase(p) {
      if (p <= 0) return 0;
      if (p >= 1) return 1;
      return 1 - Math.pow(1 - p, 4.4);
    }

    function animate(currentTime) {
      if (isSkipped) return;

      const elapsed = currentTime - startTime;
      const progress = Math.min(1, elapsed / totalDuration);
      const easeProgress = customEase(progress);

      laneConfigs.forEach(cfg => {
        const currentX = cfg.targetOffset * easeProgress;
        cfg.track.style.transform = `translate3d(-${currentX}px, 0, 0)`;
      });

      // Synchronized Tick Sound on primary lane
      const needlePosition = (laneConfigs[0].targetOffset * easeProgress) + (viewportWidth / 2);
      const currentCardIndex = Math.floor(needlePosition / totalCardWidth);

      if (currentCardIndex !== lastPassedIndex && currentCardIndex >= 0 && currentCardIndex <= laneConfigs[0].winningIndex) {
        lastPassedIndex = currentCardIndex;
        soundManager.playTick();
      }

      if (progress < 1) {
        activeAnimationId = requestAnimationFrame(animate);
      } else {
        // Complete Stop
        laneConfigs.forEach(cfg => {
          cfg.track.style.transform = `translate3d(-${cfg.targetOffset}px, 0, 0)`;
          const winCard = cfg.track.children[cfg.winningIndex];
          if (winCard) winCard.classList.add('winner-landed');
        });
        onMultiRouletteStopped(results);
      }
    }

    activeAnimationId = requestAnimationFrame(animate);
  }

  // ==================== ON STOPPED & WIN REVEAL ====================
  function onMultiRouletteStopped(results) {
    multiRouletteContainer.classList.remove('spinning');
    multiRouletteContainer.classList.add('winner-active');
    if (skipAnimationBtn) skipAnimationBtn.style.display = 'none';

    soundManager.playWin();

    setTimeout(() => {
      showMultiWinModal(results);
      resetOpenButton();
    }, 700);
  }

  // ==================== MULTI WIN MODAL ====================
  function showMultiWinModal(results) {
    const winItemsGrid = document.getElementById('winItemsGrid');
    const winModalTitle = document.getElementById('winModalTitle');
    const winModalSubtitle = document.getElementById('winModalSubtitle');
    const winTotalValueDisplay = document.getElementById('winTotalValueDisplay');
    const modalSellAllBtn = document.getElementById('modalSellAllBtn');

    winItemsGrid.innerHTML = '';
    let totalValue = 0.0;
    const invIds = [];

    results.forEach(res => {
      const item = res.won_item;
      totalValue += item.value;
      if (res.inventory_id) invIds.push(res.inventory_id);

      const card = document.createElement('div');
      card.className = 'win-single-card';
      card.style.setProperty('--card-color', item.rarity_color);

      card.innerHTML = `
        <div class="win-card-weapon">${item.weapon_type}</div>
        <div class="win-card-img-box">
          <svg class="win-card-img"><use href="#icon-${item.image_url || 'generic_weapon'}"></use></svg>
        </div>
        <div class="win-card-skin">${item.skin_name}</div>
        <div class="win-card-price">$${item.value.toFixed(2)}</div>
      `;
      winItemsGrid.appendChild(card);
    });

    if (results.length > 1) {
      winModalTitle.textContent = `🎉 ПОЗДРАВЛЯЕМ! (×${results.length})`;
      winModalSubtitle.textContent = `Вы открыли ${results.length} кейсов и выиграли:`;
    } else {
      winModalTitle.textContent = '🎉 ВЫ ВЫИГРАЛИ!';
      winModalSubtitle.textContent = 'Ваш выигрыш:';
    }

    if (winTotalValueDisplay) {
      winTotalValueDisplay.textContent = `$${totalValue.toFixed(2)}`;
    }

    if (modalSellAllBtn) {
      if (results.length === 1) {
        modalSellAllBtn.textContent = `ПРОДАТЬ ЗА $${totalValue.toFixed(2)}`;
      } else {
        modalSellAllBtn.textContent = `ПРОДАТЬ ВСЕ ЗА $${totalValue.toFixed(2)}`;
      }
      modalSellAllBtn.onclick = () => sellBatchWonItems(invIds);
    }

    const modalOpenAgainBtn = document.getElementById('modalOpenAgainBtn');
    if (modalOpenAgainBtn) {
      modalOpenAgainBtn.onclick = () => {
        winModal.classList.remove('active');
        openCaseBtn.click();
      };
    }

    winModal.classList.add('active');
  }

  async function sellBatchWonItems(invIds) {
    if (!invIds.length) return;
    try {
      let lastBalance = null;
      for (const id of invIds) {
        const res = await fetch(`/inventory/sell/${id}/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': typeof getCsrfToken === 'function' ? getCsrfToken() : (getCookie('csrftoken') || '')
          },
          credentials: 'same-origin'
        });
        const d = await res.json();
        if (d.success) lastBalance = d.new_balance;
      }
      if (lastBalance !== null) window.updateUserBalance(lastBalance);
      winModal.classList.remove('active');
    } catch (e) {
      alert('Ошибка при продаже предметов.');
    }
  }

  function resetOpenButton() {
    isOpening = false;
    openCaseBtn.disabled = false;
    openCaseBtn.classList.remove('loading');
    updateQuantity(selectedQuantity);
  }

  const closeWinModalBtn = document.getElementById('closeWinModalBtn');
  if (closeWinModalBtn) {
    closeWinModalBtn.addEventListener('click', () => {
      winModal.classList.remove('active');
    });
  }
});
