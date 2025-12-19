const copyButtons = document.querySelectorAll('[data-copy-target]');

copyButtons.forEach((button) => {
  button.addEventListener('click', async () => {
    const targetId = button.getAttribute('data-copy-target');
    const target = document.getElementById(targetId);

    if (!target) {
      return;
    }

    const textToCopy = target.textContent.trim();

    try {
      await navigator.clipboard.writeText(textToCopy);
      const originalText = button.textContent;
      button.textContent = 'Copied';
      button.classList.add('text-cyan-300');

      setTimeout(() => {
        button.textContent = originalText;
        button.classList.remove('text-cyan-300');
      }, 1500);
    } catch (error) {
      console.error('Copy failed', error);
    }
  });
});
