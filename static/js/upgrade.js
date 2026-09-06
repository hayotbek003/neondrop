/**
 * NEONDROP UPGRADE WHEEL CONTROLLER
 */

document.addEventListener('DOMContentLoaded', () => {
  let selectedInvItem = null;
  let selectedTargetItem = null;

  const invCards = document.querySelectorAll('.upgrade-inv-item');
  const targetCards = document.querySelectorAll('.upgrade-target-item');
  const chanceDisplay = document.getElementById('upgradeChanceDisplay');
  const executeBtn = document.getElementById('executeUpgradeBtn');
  const wheelNeedle = document.getElementById('upgradeWheelNeedle');
  const upgradeOutcomeBox = document.getElementById('upgradeOutcomeBox');
  const upgradeCircleGauge = document.getElementById('upgradeCircleGauge');

  // Select User Inventory Item
  invCards.forEach(card => {
    card.addEventListener('click', () => {
      invCards.forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedInvItem = {
        id: card.getAttribute('data-id'),
        value: parseFloat(card.getAttribute('data-value')),
        name: card.getAttribute('data-name'),
      };
      
      const slot = document.getElementById('sourceSlotDisplay');
      slot.innerHTML = card.innerHTML;
      updateCalculatedChance();
    });
  });

  // Select Target Catalog Item
  targetCards.forEach(card => {
    card.addEventListener('click', () => {
      targetCards.forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedTargetItem = {
        id: card.getAttribute('data-id'),
        value: parseFloat(card.getAttribute('data-value')),
        name: card.getAttribute('data-name'),
      };

      const slot = document.getElementById('targetSlotDisplay');
      slot.innerHTML = card.innerHTML;
      updateCalculatedChance();
    });
  });

  function updateCalculatedChance() {
    if (!selectedInvItem || !selectedTargetItem) {
      chanceDisplay.textContent = '0.00%';
      executeBtn.disabled = true;
      return;
    }

    if (selectedTargetItem.value <= selectedInvItem.value) {
      chanceDisplay.textContent = 'Н/Д';
      executeBtn.disabled = true;
      return;
    }

    const ratio = selectedInvItem.value / selectedTargetItem.value;
    const chance = Math.min(80.0, Math.max(1.0, ratio * 100.0 * 0.92));
    chanceDisplay.textContent = `${chance.toFixed(2)}%`;
    executeBtn.disabled = false;

    // Update circular SVG gauge stroke
    // Circumference = 2 * PI * 45 ≈ 282.74
    if (upgradeCircleGauge) {
      const strokeVal = (chance / 100.0) * 282.74;
      upgradeCircleGauge.style.strokeDasharray = `${strokeVal} 283`;
    }
  }

  // Execute Upgrade Roll
  if (executeBtn) {
    executeBtn.addEventListener('click', async () => {
      if (!selectedInvItem || !selectedTargetItem) return;

      executeBtn.disabled = true;
      executeBtn.textContent = 'КРУТИМ...';
      upgradeOutcomeBox.style.display = 'none';

      try {
        const formData = new FormData();
        formData.append('inventory_item_id', selectedInvItem.id);
        formData.append('target_item_id', selectedTargetItem.id);

        const res = await fetch('/upgrade/api/execute/', {
          method: 'POST',
          headers: {
            'X-CSRFToken': typeof getCsrfToken === 'function' ? getCsrfToken() : (getCookie('csrftoken') || '')
          },
          credentials: 'same-origin',
          body: formData
        });

        const data = await res.json();
        if (!data.success) {
          alert(data.error || 'Ошибка при проведении апгрейда.');
          executeBtn.disabled = false;
          executeBtn.textContent = 'УЛУЧШИТЬ СКИН';
          return;
        }

        // Spin needle animation
        if (wheelNeedle) {
          wheelNeedle.style.transition = 'transform 4.5s cubic-bezier(0.12, 0.8, 0.33, 1)';
          wheelNeedle.style.transform = `rotate(${data.target_deg}deg)`;
        }

        setTimeout(() => {
          if (data.is_won) {
            window.soundFX.playWin();
            upgradeOutcomeBox.className = 'upgrade-result-banner win';
            const priceStr = window.formatUC ? window.formatUC(data.target_item.value) : `${data.target_item.value} UC`;
            upgradeOutcomeBox.innerHTML = `🎉 ПОБЕДА! Вы получили: <strong>${data.target_item.name} (${priceStr})</strong>`;
          } else {
            upgradeOutcomeBox.className = 'upgrade-result-banner lose';
            upgradeOutcomeBox.innerHTML = `💀 НЕУДАЧА. Предмет сгорел. Выпало: ${data.roll}%, требовалось <= ${data.chance}%`;
          }
          upgradeOutcomeBox.style.display = 'block';

          setTimeout(() => {
            window.location.reload();
          }, 3000);

        }, 4600);

      } catch (e) {
        alert('Ошибка связи с сервером.');
        executeBtn.disabled = false;
        executeBtn.textContent = 'УЛУЧШИТЬ СКИН';
      }
    });
  }
});
