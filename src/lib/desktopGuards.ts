function isReloadShortcut(event: KeyboardEvent): boolean {
  if (event.key === 'F5') return true;
  const modifier = event.ctrlKey || event.metaKey;
  return modifier && event.key.toLowerCase() === 'r';
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest('input, textarea, select, [contenteditable="true"]'));
}

export function installDesktopPageGuards(): void {
  window.addEventListener('keydown', (event) => {
    if (isReloadShortcut(event)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  window.addEventListener('contextmenu', (event) => {
    if (isEditableTarget(event.target)) return;
    event.preventDefault();
  });
}
