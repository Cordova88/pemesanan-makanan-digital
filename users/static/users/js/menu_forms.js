document.querySelectorAll('[data-choice-picker]').forEach((picker) => {
  const search = picker.querySelector('[data-choice-search]');
  const count = picker.querySelector('[data-choice-count]');
  const empty = picker.querySelector('[data-choice-empty]');
  const options = Array.from(picker.querySelectorAll('[data-choice-option]'));
  const update = () => {
    const query = search.value.trim().toLocaleLowerCase('id');
    let selected = 0;
    let visible = 0;
    options.forEach((option) => {
      const checked = option.querySelector('input[type="checkbox"]').checked;
      selected += Number(checked);
      // Keep selected choices visible so searching never conceals current selections.
      option.hidden = !checked && !option.textContent.toLocaleLowerCase('id').includes(query);
      visible += Number(!option.hidden);
    });
    count.textContent = `${selected} dipilih`;
    empty.hidden = visible > 0 || options.length === 0;
  };
  search.addEventListener('input', update);
  picker.addEventListener('change', update);
  update();
});

document.querySelectorAll('[data-menu-editor]').forEach((editor) => {
  const input = editor.querySelector('[data-menu-image-input]');
  const preview = editor.querySelector('[data-menu-image-preview]');
  const empty = editor.querySelector('[data-menu-image-empty]');
  const clear = editor.querySelector('input[name="image-clear"]');
  const original = preview.getAttribute('src');
  let objectUrl;
  const update = () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = undefined;
    const file = input.files[0];
    let source = original;
    if (file) {
      objectUrl = URL.createObjectURL(file);
      source = objectUrl;
    } else if (clear && clear.checked) {
      source = null;
    }
    preview.hidden = !source;
    empty.hidden = Boolean(source);
    if (source) preview.src = source;
    else preview.removeAttribute('src');
  };
  input.addEventListener('change', update);
  if (clear) clear.addEventListener('change', update);
  window.addEventListener('pagehide', () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  });
});
