const themes = ['coral', 'peach', 'peach-alt', 'coral-alt'];
export function menuTheme(item) {
  const id = Number(item.menu_item_id ?? item.id);
  if (Number.isSafeInteger(id) && id > 0) return themes[(id - 1) % themes.length];
  const key = String(item.category || 'menu') + ':' + String(item.id || 'default');
  let hash = 0;
  for (const character of key) hash = (hash * 31 + character.codePointAt(0)) >>> 0;
  return themes[hash % themes.length];
}

/**
 * Tells transparent cut-out photos (designed to float over the card) apart from
 * ordinary opaque photos, which must stay clipped inside the card instead.
 */
export class PhotoShapeProbe {
  static #cache = new Map();
  static #sampleSize = 32;
  static #minTransparentShare = 0.02;

  /** True when the loaded image has visible transparency (or cannot be inspected). */
  static isCutout(image) {
    const key = image.currentSrc || image.src;
    if (PhotoShapeProbe.#cache.has(key)) return PhotoShapeProbe.#cache.get(key);
    const result = PhotoShapeProbe.#measure(image);
    PhotoShapeProbe.#cache.set(key, result);
    return result;
  }

  static #measure(image) {
    const size = PhotoShapeProbe.#sampleSize;
    try {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = size;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(image, 0, 0, size, size);
      const pixels = context.getImageData(0, 0, size, size).data;
      let transparent = 0;
      for (let index = 3; index < pixels.length; index += 4) if (pixels[index] < 250) transparent++;
      return transparent / (size * size) >= PhotoShapeProbe.#minTransparentShare;
    } catch {
      // Cross-origin media without CORS cannot be read; keep the original floating style.
      return true;
    }
  }
}

/** Photo URL comes from the API. Decorative layers never contain menu data. */
export function createMenuCard(item, { onSelect, eager = false } = {}) {
  const card = document.createElement('article');
  card.className = 'food-card';
  card.dataset.theme = menuTheme(item);
  const art = createFoodVisual(item, { eager });
  const content = document.createElement('div');
  content.className = 'food-card__content';
  const name = document.createElement('h3');
  name.className = 'food-card__name';
  name.textContent = String(item.name || 'Menu');
  name.title = name.textContent;
  const description = document.createElement('p');
  description.className = 'food-card__description';
  description.textContent = item.description || 'Dibuat segar untukmu hari ini.';
  const footer = document.createElement('div');
  footer.className = 'food-card__footer';
  const price = document.createElement('strong');
  price.className = 'food-card__price';
  price.textContent = 'Rp' + Number(item.price || 0).toLocaleString('id-ID');
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'food-card__add';
  button.dataset.menuId = item.id;
  button.setAttribute('aria-label', `Pilih ${name.textContent}`);
  button.textContent = '+';
  if (onSelect) button.addEventListener('click', () => onSelect(item.id));
  footer.append(price, button);
  content.append(name, description, footer);
  card.append(art, content);
  return card;
}

export function createFoodVisual(item, { eager = false, decorated = true } = {}) {
  const art = document.createElement('div');
  art.className = 'food-card__art';
  art.dataset.theme = menuTheme(item);
  const blob = document.createElement('span');
  blob.className = 'food-card__blob';
  blob.setAttribute('aria-hidden', 'true');
  const placeholder = document.createElement('span');
  placeholder.className = 'food-card__placeholder';
  placeholder.textContent = 'Foto belum tersedia';
  if (decorated) art.append(blob);
  art.append(placeholder);
  if (item.image_url) {
    const image = document.createElement('img');
    image.className = 'food-card__image';
    image.alt = String(item.name || 'Menu');
    image.width = image.height = 320;
    image.loading = eager ? 'eager' : 'lazy';
    image.decoding = 'async';
    image.addEventListener('load', () => {
      art.classList.toggle('food-card__art--photo', !PhotoShapeProbe.isCutout(image));
      placeholder.hidden = true;
      image.classList.add('is-loaded');
    }, { once: true });
    image.addEventListener('error', () => { image.remove(); placeholder.hidden = false; }, { once: true });
    image.src = item.image_url;
    art.append(image);
  }
  return art;
}

export function createDetailPhoto(item, { eager = true } = {}) {
  // Customer screens share the cutout photo; legacy detail uploads stay stored.
  const art = createFoodVisual(item, { eager });
  art.classList.add('food-detail-photo');
  return art;
}
