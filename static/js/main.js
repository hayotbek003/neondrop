/**
 * NEONDROP MAIN JAVASCRIPT
 * Global Utilities, Web Audio Synthesizer, CSRF Helpers, Live Drop Streamer, Mobile Drawer
 */

// Dynamic CSRF Token and Cookie Helper
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function getCsrfToken() {
  const fromCookie = getCookie('csrftoken');
  if (fromCookie) return fromCookie;

  const metaEl = document.querySelector('meta[name="csrf-token"]');
  if (metaEl && metaEl.getAttribute('content')) {
    return metaEl.getAttribute('content');
  }

  const inputEl = document.querySelector('input[name="csrfmiddlewaretoken"]');
  if (inputEl && inputEl.value) {
    return inputEl.value;
  }

  return '';
}

window.getCookie = getCookie;
window.getCsrfToken = getCsrfToken;

// Web Audio API Synthesizer (No external audio file dependencies!)
class NeonSoundFX {
  constructor() {
    this.ctx = null;
  }

  init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) this.ctx = new AudioCtx();
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  playTick() {
    try {
      this.init();
      if (!this.ctx) return;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(440, this.ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(120, this.ctx.currentTime + 0.04);
      
      gain.gain.setValueAtTime(0.12, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.04);
      
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      
      osc.start();
      osc.stop(this.ctx.currentTime + 0.04);
    } catch (e) {}
  }

  playWin() {
    try {
      this.init();
      if (!this.ctx) return;
      const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
      notes.forEach((freq, i) => {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, this.ctx.currentTime + i * 0.1);
        
        gain.gain.setValueAtTime(0.2, this.ctx.currentTime + i * 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + i * 0.1 + 0.35);
        
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        
        osc.start(this.ctx.currentTime + i * 0.1);
        osc.stop(this.ctx.currentTime + i * 0.1 + 0.35);
      });
    } catch (e) {}
  }
}

window.soundFX = new NeonSoundFX();

// Currency Format Helpers
function formatUC(amount, suffix = true) {
  if (amount === null || amount === undefined) return suffix ? '0 UC' : '0';
  const num = parseFloat(amount);
  if (isNaN(num)) return suffix ? '0 UC' : '0';
  const isWhole = num % 1 === 0;
  const valStr = isWhole ? Math.round(num).toLocaleString('ru-RU') : num.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return suffix ? `${valStr} UC` : valStr;
}

function formatUsdApprox(amount) {
  if (amount === null || amount === undefined) return '≈ $0.00';
  const num = parseFloat(amount);
  if (isNaN(num)) return '≈ $0.00';
  const rate = (window.NEONDROP_CURRENCY && window.NEONDROP_CURRENCY.ucToUsdRate) ? window.NEONDROP_CURRENCY.ucToUsdRate : (250.0 / 12000.0);
  const usdVal = num * rate;
  return `≈ $${usdVal.toFixed(2)}`;
}

function renderUcBadgeHtml(amount, showUsd = true, size = 16) {
  const ucText = formatUC(amount);
  const usdText = formatUsdApprox(amount);
  const iconUrl = (window.NEONDROP_CURRENCY && window.NEONDROP_CURRENCY.ucIconUrl) ? window.NEONDROP_CURRENCY.ucIconUrl : '/static/images/uc_icon.png';
  const usdHtml = showUsd ? `<span class="usd-approx">${usdText}</span>` : '';
  return `<span class="uc-price-wrap"><span class="uc-badge"><img src="${iconUrl}" class="uc-icon" width="${size}" height="${size}" alt="UC" /><span class="uc-val">${ucText}</span></span>${usdHtml}</span>`;
}

window.formatUC = formatUC;
window.formatUsdApprox = formatUsdApprox;
window.renderUcBadgeHtml = renderUcBadgeHtml;

// Live Drops Ticker Poller
function initLiveDrops() {
  const tickerTrack = document.getElementById('liveDropsTrack');
  if (!tickerTrack) return;

  function fetchDrops() {
    fetch('/api/live-drops/')
      .then(res => res.json())
      .then(data => {
        if (data.success && data.drops && data.drops.length > 0) {
          const iconUrl = (window.NEONDROP_CURRENCY && window.NEONDROP_CURRENCY.ucIconUrl) ? window.NEONDROP_CURRENCY.ucIconUrl : '/static/images/uc_icon.png';
          let html = '';
          data.drops.forEach(drop => {
            const formattedVal = formatUC(drop.item_value);
            const usdApprox = formatUsdApprox(drop.item_value);
            html += `
              <div class="drop-item-chip" style="border-bottom-color: ${drop.rarity_color}">
                <img src="${drop.user_avatar}" class="drop-chip-user-avatar" alt="${drop.username}">
                <svg class="drop-chip-weapon-icon"><use href="#icon-${drop.image_url || 'generic_weapon'}"></use></svg>
                <div class="drop-chip-info">
                  <span class="drop-chip-name">${drop.item_name}</span>
                  <span class="drop-chip-price"><img src="${iconUrl}" class="uc-icon-sm" alt="UC"> ${formattedVal}</span>
                </div>
              </div>
            `;
          });
          tickerTrack.innerHTML = html + html;
        }
      })
      .catch(() => {});
  }

  setInterval(fetchDrops, 15000);
}

// Mobile Side Drawer Controller
function initMobileDrawer() {
  const openBtn = document.getElementById('mobileDrawerOpen');
  const closeBtn = document.getElementById('mobileDrawerClose');
  const backdrop = document.getElementById('mobileDrawerBackdrop');
  const drawer = document.getElementById('mobileDrawer');

  function openDrawer() {
    if (drawer && backdrop) {
      drawer.classList.add('open');
      backdrop.classList.add('open');
      document.body.style.overflow = 'hidden';
    }
  }

  function closeDrawer() {
    if (drawer && backdrop) {
      drawer.classList.remove('open');
      backdrop.classList.remove('open');
      document.body.style.overflow = '';
    }
  }

  if (openBtn) openBtn.addEventListener('click', openDrawer);
  if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
  if (backdrop) backdrop.addEventListener('click', closeDrawer);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDrawer();
  });
}

// Update Balance UI everywhere
window.updateUserBalance = function(newBalance) {
  const balanceElements = document.querySelectorAll('.user-balance-val');
  balanceElements.forEach(el => {
    el.textContent = formatUC(newBalance);
  });

  const usdElements = document.querySelectorAll('.user-balance-usd');
  usdElements.forEach(el => {
    el.textContent = formatUsdApprox(newBalance);
  });
};

// Withdrawal Modal Controller
function initWithdrawalModal() {
  const modal = document.getElementById('withdrawalModal');
  const backdrop = document.getElementById('withdrawalModalBackdrop');
  const closeBtn = document.getElementById('closeWithdrawalModalBtn');
  const triggers = document.querySelectorAll('.open-withdraw-modal-trigger');
  const form = document.getElementById('withdrawalForm');
  const amountInput = document.getElementById('withdrawAmount');
  const withdrawAllBtn = document.getElementById('withdrawAllBtn');
  const startWithdrawBtn = document.getElementById('startWithdrawBtn');
  const confirmStep = document.getElementById('withdrawConfirmStep');
  const confirmAmountDisplay = document.getElementById('confirmAmountDisplay');
  const cancelConfirmBtn = document.getElementById('withdrawCancelConfirmBtn');
  const finalSubmitBtn = document.getElementById('withdrawFinalSubmitBtn');
  const successNotice = document.getElementById('withdrawSuccessNotice');
  const errorNotice = document.getElementById('withdrawErrorNotice');
  const createdIdSpan = document.getElementById('createdWithdrawalId');
  const tgLink = document.getElementById('withdrawTgLink');

  if (!modal || !backdrop) return;

  function getUserBalance() {
    const balanceEl = document.querySelector('.user-balance-val');
    if (!balanceEl) return 0;
    const raw = balanceEl.textContent.replace(/[^0-9.,]/g, '').replace(',', '.');
    const parsed = parseFloat(raw);
    return isNaN(parsed) ? 0 : parsed;
  }

  function updateUserBalance(newBal) {
    document.querySelectorAll('.user-balance-val').forEach(el => {
      el.textContent = typeof newBal === 'number' ? newBal.toLocaleString('ru-RU') : newBal;
    });
  }

  function showError(msg) {
    if (errorNotice) {
      errorNotice.textContent = msg;
      errorNotice.style.display = 'block';
    }
  }

  function checkAmountValidity() {
    const val = parseFloat(amountInput ? amountInput.value : 0);
    if (startWithdrawBtn) {
      if (isNaN(val) || val < 60) {
        startWithdrawBtn.disabled = true;
        startWithdrawBtn.style.opacity = '0.5';
        startWithdrawBtn.style.cursor = 'not-allowed';
      } else {
        startWithdrawBtn.disabled = false;
        startWithdrawBtn.style.opacity = '1';
        startWithdrawBtn.style.cursor = 'pointer';
      }
    }
  }

  function openModal() {
    modal.style.display = 'block';
    backdrop.style.display = 'block';
    setTimeout(() => {
      modal.classList.add('show');
      backdrop.classList.add('active');
    }, 10);
    document.body.style.overflow = 'hidden';

    if (errorNotice) {
      errorNotice.style.display = 'none';
      errorNotice.textContent = '';
    }
    if (successNotice) successNotice.style.display = 'none';
    if (confirmStep) confirmStep.style.display = 'none';
    if (form) form.style.display = 'flex';
    checkAmountValidity();
  }

  function closeModal() {
    modal.classList.remove('show');
    backdrop.classList.remove('active');
    setTimeout(() => {
      modal.style.display = 'none';
      backdrop.style.display = 'none';
    }, 250);
    document.body.style.overflow = '';
  }

  triggers.forEach(trig => {
    trig.addEventListener('click', (e) => {
      e.preventDefault();
      openModal();
    });
  });

  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (backdrop) backdrop.addEventListener('click', closeModal);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('show')) {
      closeModal();
    }
  });

  if (amountInput) {
    amountInput.addEventListener('input', checkAmountValidity);
  }

  if (withdrawAllBtn && amountInput) {
    withdrawAllBtn.addEventListener('click', () => {
      const bal = Math.floor(getUserBalance());
      if (bal > 0) {
        amountInput.value = bal;
        checkAmountValidity();
      }
    });
  }

  // Step 1: User clicks "ВЫВЕСТИ ЧЕРЕЗ TELEGRAM" -> validate and show confirmation
  if (startWithdrawBtn) {
    startWithdrawBtn.addEventListener('click', () => {
      const amountVal = parseFloat(amountInput.value);
      const detailsInput = document.getElementById('withdrawDetails');

      if (errorNotice) {
        errorNotice.style.display = 'none';
        errorNotice.textContent = '';
      }

      if (isNaN(amountVal) || amountVal < 60) {
        showError('Минимальная сумма вывода — 60 UC.');
        return;
      }

      if (amountVal % 1 !== 0) {
        showError('Сумма вывода должна быть целым числом UC.');
        return;
      }

      const currentBal = getUserBalance();
      if (amountVal > currentBal) {
        showError(`Недостаточно средств. Ваш баланс: ${Math.floor(currentBal)} UC, запрошено: ${amountVal} UC.`);
        return;
      }

      if (!detailsInput || !detailsInput.value.trim()) {
        showError('Пожалуйста, укажите ваши реквизиты.');
        return;
      }

      if (confirmAmountDisplay) {
        confirmAmountDisplay.textContent = amountVal;
      }
      form.style.display = 'none';
      if (confirmStep) confirmStep.style.display = 'block';
    });
  }

  // Confirmation Step: Cancel
  if (cancelConfirmBtn) {
    cancelConfirmBtn.addEventListener('click', () => {
      if (confirmStep) confirmStep.style.display = 'none';
      if (form) form.style.display = 'flex';
      checkAmountValidity();
    });
  }

  // Confirmation Step: Final Submit -> Deduct immediately
  if (finalSubmitBtn) {
    finalSubmitBtn.addEventListener('click', async () => {
      if (errorNotice) errorNotice.style.display = 'none';
      finalSubmitBtn.disabled = true;
      finalSubmitBtn.style.opacity = '0.7';
      finalSubmitBtn.textContent = 'Списание UC...';

      try {
        const formData = new FormData(form);
        const res = await fetch('/deposit/api/create-withdrawal/', {
          method: 'POST',
          headers: {
            'X-CSRFToken': typeof getCsrfToken === 'function' ? getCsrfToken() : (getCookie('csrftoken') || '')
          },
          credentials: 'same-origin',
          body: formData
        });

        const data = await res.json();
        if (data.success && data.telegram_url) {
          if (createdIdSpan) createdIdSpan.textContent = data.withdrawal_id;
          if (tgLink) tgLink.href = data.telegram_url;

          // Update header and profile balance elements immediately
          if (data.balance_after !== undefined) {
            updateUserBalance(data.balance_after);
          }

          if (confirmStep) confirmStep.style.display = 'none';
          if (form) form.style.display = 'none';
          if (successNotice) successNotice.style.display = 'block';

          // Open Telegram deep link in new tab or fallback to redirect
          const tgWindow = window.open(data.telegram_url, '_blank');
          if (!tgWindow || tgWindow.closed || typeof tgWindow.closed === 'undefined') {
            window.location.href = data.telegram_url;
          }
        } else {
          if (confirmStep) confirmStep.style.display = 'none';
          if (form) form.style.display = 'flex';
          showError(data.error || 'Ошибка при создании заявки');
        }
      } catch (err) {
        if (confirmStep) confirmStep.style.display = 'none';
        if (form) form.style.display = 'flex';
        showError('Ошибка соединения с сервером. Попробуйте позже.');
      } finally {
        finalSubmitBtn.disabled = false;
        finalSubmitBtn.style.opacity = '1';
        finalSubmitBtn.textContent = 'ПОДТВЕРДИТЬ ВЫВОД';
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initLiveDrops();
  initMobileDrawer();
  initWithdrawalModal();
  
  // Unlock audio on first user click
  document.body.addEventListener('click', () => {
    window.soundFX.init();
  }, { once: true });
});

