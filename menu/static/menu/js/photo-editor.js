/* Shared CMS/Admin preview. Server validation remains authoritative. */
(function () {
  async function initialize(editor) {
    if (editor.dataset.photoInitialized) return;
    editor.dataset.photoInitialized = 'true';
    const input = editor.querySelector('input[type=file]');
    const form = editor.closest('form');
    if (!input || !form) return;
    const mount = editor.querySelector('[data-photo-card]');
    const selection = editor.querySelector('[data-photo-selection]');
    const status = editor.querySelector('[data-photo-status]');
    const error = editor.querySelector('[data-photo-error]');
    const clear = editor.querySelector('input[type=checkbox]');
    const initial = editor.dataset.photoOriginal || '';
    let objectUrl = '', selectedFile, revision = 0;
    let createMenuCard, createDetailPhoto, createFoodVisual;
    try { ({ createMenuCard, createDetailPhoto, createFoodVisual } = await import(editor.dataset.photoModule)); }
    catch { return; } // Saved photo and file input remain usable without modules.
    const cleanup = () => { if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = ''; };
    const reportError = message => {
      error.textContent = message;
      error.hidden = !message;
      input.setCustomValidity(message);
    };
    function render() {
      const generation = ++revision;
      const isDetail = editor.dataset.photoKind === 'detail';
      const file = input.files[0];
      if (file !== selectedFile) { cleanup(); selectedFile = file; }
      reportError('');
      let url = clear?.checked ? '' : initial;
      status.textContent = clear?.checked ? 'Foto akan dilepas setelah disimpan. File lama tetap dipertahankan.' : initial ? 'Foto tersimpan. Pilih file untuk menggantinya.' : isDetail ? 'Belum ada foto arsip.' : 'Belum ada foto. Kartu akan memakai gambar pengganti.';
      if (file && clear?.checked) {
        reportError('Pilih mengganti foto atau melepas foto, bukan keduanya.');
      } else if (file) {
        if (file.size > 10 * 1024 * 1024) {
          reportError('Ukuran foto maksimal 10 MB.');
        } else if (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
          reportError('Gunakan foto JPEG, PNG, atau WebP.');
        } else {
          if (!objectUrl) objectUrl = URL.createObjectURL(file);
          url = objectUrl;
          status.textContent = 'Pratinjau foto yang dipilih; perubahan belum disimpan.';
        }
      }
      const name = form.querySelector('[name=name]')?.value || 'Nama menu';
      const price = form.querySelector('[name=price]')?.value || '0';
      const category = form.querySelector('[name=category]');
      const item = {
        id: Number(editor.dataset.menuId) || 1, name, price,
        description: form.querySelector('[name=description]')?.value || 'Deskripsi menu',
        category: category?.selectedOptions?.[0]?.textContent || '', image_url: url,
      };
      const card = isDetail ? createFoodVisual(item, { eager: true, decorated: false }) : createMenuCard(item, { eager: true });
      mount.classList.toggle('menu-photo-editor__card--detail', isDetail);
      const button = card.querySelector('button');
      if (button) { button.disabled = true; button.tabIndex = -1; }
      const photo = card.querySelector('img');
      if (photo && url === objectUrl) {
        photo.addEventListener('load', () => {
          if (generation !== revision) return;
          if (photo.naturalWidth * photo.naturalHeight > 20000000 || Math.max(photo.naturalWidth, photo.naturalHeight) > 10000) reportError('Foto maksimal 20 juta piksel dan 10.000 piksel per sisi.');
        }, { once: true });
        photo.addEventListener('error', () => {
          if (generation === revision) reportError('Foto tidak dapat ditampilkan. Periksa file atau pilih foto lain.');
        }, { once: true });
      }
      mount.replaceChildren(card);
      mount.hidden = false;
      if (selection) {
        const caption = document.createElement('p');
        caption.textContent = 'Foto pada pilihan menu';
        selection.replaceChildren(caption, createDetailPhoto(item));
        selection.hidden = false;
      }
      const staticPhoto = editor.querySelector('[data-photo-static]');
      if (staticPhoto) staticPhoto.hidden = true;
    }
    input.addEventListener('change', render);
    clear?.addEventListener('change', render);
    form.querySelectorAll('[name=name],[name=price],[name=description],[name=category]').forEach(field => field.addEventListener('input', render));
    form.addEventListener('reset', () => setTimeout(render, 0));
    window.addEventListener('pagehide', cleanup);
    window.addEventListener('pageshow', render);
    render();
  }
  function start() { document.querySelectorAll('[data-photo-editor]').forEach(initialize); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
}());
