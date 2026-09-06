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
  const usdHtml = showUsd ? `<span class="usd-approx">${usdText}</span>` : '';
  return `<span class="uc-price-wrap"><span class="uc-badge"><img src="/static/images/uc_icon.svg" class="uc-icon" width="${size}" height="${size}" alt="UC" /><span class="uc-val">${ucText}</span></span>${usdHtml}</span>`;
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
                  <span class="drop-chip-price"><img src="/static/images/uc_icon.svg" class="uc-icon-sm" alt="UC"> ${formattedVal}</span>
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

document.addEventListener('DOMContentLoaded', () => {
  initLiveDrops();
  initMobileDrawer();
  
  // Unlock audio on first user click
  document.body.addEventListener('click', () => {
    window.soundFX.init();
  }, { once: true });
});
