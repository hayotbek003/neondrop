/**
 * NEONDROP CS:GO STYLE ROULETTE & SOUND ENGINE
 * Precise server-aligned tape, physically synchronized ticks & audio controls
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

    // Local Audio Element instances
    this.startAudio = this.createAudioElement('/static/sounds/roulette_start.mp3');
    this.winAudio = this.createAudioElement('/static/sounds/roulette_win.mp3');
    
    // Pool of tick audio elements for rapid non-overlapping playback
    this.tickPoolSize = 5;
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
      this.startAudio.play().catch(() => {
        this.synthStart();
      });
    } else {
      this.synthStart();
    }
  }

  playTick() {
    if (this.isMuted) return;
    this.initAudioContext();

    // Use pooled audio element for zero-latency consecutive clicks
    const audio = this.tickPool[this.tickPoolIndex];
    this.tickPoolIndex = (this.tickPoolIndex + 1) % this.tickPoolSize;

    if (audio) {
      audio.currentTime = 0;
      audio.play().catch(() => {
        this.synthTick();
      });
    } else {
      this.synthTick();
    }
  }

  playWin() {
    if (this.isMuted) return;
    this.initAudioContext();

    if (this.winAudio) {
      this.winAudio.currentTime = 0;
      this.winAudio.play().catch(() => {
        this.synthWin();
      });
    } else {
      this.synthWin();
    }
  }

  // ==================== SYNTHESIZED FALLBACKS (Web Audio API) ====================
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
      const chords = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
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

// ==================== ROULETTE CONTROLLER ====================
document.addEventListener('DOMContentLoaded', () => {
  const openCaseBtn = document.getElementById('openCaseBtn');
  const rouletteContainer = document.getElementById('rouletteContainer');
  const rouletteTrack = document.getElementById('rouletteTrack');
  const rouletteViewport = document.getElementById('rouletteViewport');
  const rouletteStatusBar = document.getElementById('rouletteStatusBar');
  const winModal = document.getElementById('winModal');
  const caseSlug = openCaseBtn ? openCaseBtn.getAttribute('data-case-slug') : null;

  if (!openCaseBtn || !caseSlug) return;

  const soundManager = new RouletteSoundManager();

  let isOpening = false;
  let lastWonItem = null;
  let lastInvId = null;
  let animFrameId = null;

  openCaseBtn.addEventListener('click', async () => {
    if (isOpening) return;
    isOpening = true;

    soundManager.initAudioContext();

    openCaseBtn.disabled = true;
    openCaseBtn.classList.add('loading');
    openCaseBtn.innerHTML = '<span>ОТКРЫВАЕМ...</span>';

    rouletteContainer.style.display = 'block';
    rouletteContainer.classList.remove('winner-active');
    rouletteContainer.classList.add('spinning');
    rouletteStatusBar.style.display = 'block';

    // Scroll smoothly to roulette viewport
    rouletteContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });

    try {
      // 1. Django Backend Authoritative Result
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

      // Update Live Balance across header
      window.updateUserBalance(data.new_balance);

      lastWonItem = data.won_item;
      lastInvId = data.inventory_id;

      // 2. Build Ribbon Tape
      buildRouletteTrack(data.tape, data.winning_index);

      // 3. Play Start Sound
      soundManager.playStart();

      // 4. Start Physics Spin
      setTimeout(() => {
        spinRoulettePhysics(data.winning_index, data.won_item, lastInvId);
      }, 80);

    } catch (err) {
      console.error(err);
      alert('Произошла ошибка соединения с сервером.');
      resetOpenButton();
    }
  });

  function buildRouletteTrack(tape, winningIndex) {
    rouletteTrack.style.transition = 'none';
    rouletteTrack.style.transform = 'translate3d(0px, 0, 0)';
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

  function spinRoulettePhysics(winningIndex, wonItem, invId) {
    if (!rouletteTrack.children.length) return;

    const firstCard = rouletteTrack.children[0];
    const cardStyle = window.getComputedStyle(firstCard);
    const cardWidth = firstCard.offsetWidth;
    const cardMargin = parseFloat(cardStyle.marginLeft) + parseFloat(cardStyle.marginRight);
    const totalCardWidth = cardWidth + cardMargin;

    const viewportWidth = rouletteViewport.offsetWidth;

    // Small realistic sub-pixel jitter within center card (+- 30% card width)
    const jitter = (Math.random() - 0.5) * (cardWidth * 0.6);

    // Exact landing target offset to align winning card under center needle
    const targetOffset = (winningIndex * totalCardWidth) + (totalCardWidth / 2) - (viewportWidth / 2) + jitter;

    // Duration: 7.4s +- 0.2s
    const totalDuration = 7400 + (Math.random() * 400 - 200);

    const startTime = performance.now();
    let lastPassedIndex = -1;

    // Custom multi-stage physics easing:
    // 0.0 - 0.5s: Acceleration
    // 0.5 - 3.5s: Fast spin
    // 3.5 - 6.5s: Progressive deceleration
    // 6.5 - 7.4s: Final slow ticks
    function customEase(p) {
      if (p <= 0) return 0;
      if (p >= 1) return 1;
      // High-precision smooth deceleration curve (quartic ease-out tailored for CS:GO wheel)
      return 1 - Math.pow(1 - p, 4.2);
    }

    function animate(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(1, elapsed / totalDuration);
      const easeProgress = customEase(progress);

      const currentX = targetOffset * easeProgress;
      rouletteTrack.style.transform = `translate3d(-${currentX}px, 0, 0)`;

      // Real-time Card Tick Tracking:
      // Trigger tick each time a card boundary crosses the center needle position
      const needlePositionOnTape = currentX + (viewportWidth / 2);
      const currentCardIndex = Math.floor(needlePositionOnTape / totalCardWidth);

      if (currentCardIndex !== lastPassedIndex && currentCardIndex >= 0 && currentCardIndex <= winningIndex) {
        lastPassedIndex = currentCardIndex;
        soundManager.playTick();
      }

      if (progress < 1) {
        animFrameId = requestAnimationFrame(animate);
      } else {
        // Complete Stop
        rouletteTrack.style.transform = `translate3d(-${targetOffset}px, 0, 0)`;
        onRouletteStopped(winningIndex, wonItem, invId);
      }
    }

    animFrameId = requestAnimationFrame(animate);
  }

  function onRouletteStopped(winningIndex, wonItem, invId) {
    rouletteContainer.classList.remove('spinning');
    rouletteContainer.classList.add('winner-active');

    // Play victory sound
    soundManager.playWin();

    // Highlight winning card on the ribbon
    const winningCard = rouletteTrack.children[winningIndex];
    if (winningCard) {
      winningCard.classList.add('winner-landed');
    }

    // Reveal winning modal after flash
    setTimeout(() => {
      showWinModal(wonItem, invId);
      resetOpenButton();
    }, 750);
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

    const openAgainBtn = document.getElementById('modalOpenAgainBtn');
    if (openAgainBtn) {
      openAgainBtn.onclick = () => {
        winModal.classList.remove('active');
        openCaseBtn.click();
      };
    }

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
