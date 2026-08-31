/**
 * NEONDROP CASE BATTLES CONTROLLER
 */

document.addEventListener('DOMContentLoaded', () => {
  const createBattleBtn = document.getElementById('openCreateBattleModalBtn');
  const createBattleModal = document.getElementById('createBattleModal');
  const closeCreateBattleBtn = document.getElementById('closeCreateBattleModalBtn');
  const submitBattleForm = document.getElementById('submitBattleForm');

  if (createBattleBtn && createBattleModal) {
    createBattleBtn.addEventListener('click', () => {
      createBattleModal.classList.add('active');
    });
  }

  if (closeCreateBattleBtn && createBattleModal) {
    closeCreateBattleBtn.addEventListener('click', () => {
      createBattleModal.classList.remove('active');
    });
  }

  if (submitBattleForm) {
    submitBattleForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(submitBattleForm);

      try {
        const res = await fetch('/battles/api/create/', {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken')
          },
          body: formData
        });

        const data = await res.json();
        if (data.success) {
          window.location.href = data.redirect_url;
        } else {
          alert(data.error || 'Ошибка при создании битвы.');
        }
      } catch (err) {
        alert('Ошибка связи с сервером.');
      }
    });
  }

  // Join Battle Buttons
  document.querySelectorAll('.btn-join-battle').forEach(btn => {
    btn.addEventListener('click', async () => {
      const battleId = btn.getAttribute('data-id');
      try {
        const res = await fetch(`/battles/api/join/${battleId}/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken')
          }
        });
        const data = await res.json();
        if (data.success) {
          window.location.href = data.redirect_url;
        } else {
          alert(data.error || 'Не удалось присоединиться к битве.');
        }
      } catch (e) {
        alert('Ошибка связи с сервером.');
      }
    });
  });
});
