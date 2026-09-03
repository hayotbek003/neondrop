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
            html += `
              <div class="drop-item-chip" style="border-bottom-color: ${drop.rarity_color}">
                <img src="${drop.user_avatar}" class="drop-chip-user-avatar" alt="${drop.username}">
                <svg class="drop-chip-weapon-icon"><use href="#icon-${drop.image_url || 'generic_weapon'}"></use></svg>
                <div class="drop-chip-info">
                  <span class="drop-chip-name">${drop.item_name}</span>
                  <span class="drop-chip-price">$${drop.item_value.toFixed(2)}</span>
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
    el.textContent = `$${parseFloat(newBalance).toFixed(2)}`;
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
