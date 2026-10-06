import { money } from "./api.mjs";
import { state } from "./state.mjs";

const fallbackImage =
  "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=600&q=80";
const categoryImages = {
  makanan:
    "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?auto=format&fit=crop&w=600&q=80",
  minuman:
    "https://images.unsplash.com/photo-1544145945-f90425340c7e?auto=format&fit=crop&w=600&q=80",
};

function menuImage(item) {
  return (
    item.image_url ||
    categoryImages[item.category.toLowerCase()] ||
    fallbackImage
  );
}

function renderMenu() {
  const query = document.querySelector("#search").value.toLowerCase();
  const filtered = state.menu.filter(
    (item) =>
      (state.category === "Semua" || item.category === state.category) &&
      item.name.toLowerCase().includes(query),
  );
  const grid = document.querySelector("#menuGrid");
  document.querySelector("#menuCount").textContent = `${filtered.length} menu`;
  grid.replaceChildren();

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "col-12 text-center py-5 text-secondary";
    empty.textContent = "Menu tidak ditemukan.";
    grid.append(empty);
    return;
  }

  filtered.forEach((item) => {
    const column = document.createElement("div");
    column.className = "col-6 col-md-4 col-lg-3";
    const card = document.createElement("article");
    card.className = "card menu-card h-100 bg-white p-2";
    const cover = document.createElement("div");
    cover.className = "food-cover mb-2";
    const image = document.createElement("img");
    image.src = menuImage(item);
    image.alt = item.name;
    image.loading = "lazy";
    image.addEventListener("error", () => {
      image.src = fallbackImage;
    }, { once: true });
    cover.append(image);

    const body = document.createElement("div");
    body.className = "card-body p-1 d-flex flex-column";
    const category = document.createElement("span");
    category.className =
      "badge bg-light text-secondary border w-auto align-self-start mb-1";
    category.style.fontSize = "0.7rem";
    category.textContent = item.category;
    const name = document.createElement("h3");
    name.className = "h6 fw-bold mb-1 text-truncate";
    name.textContent = item.name;
    const description = document.createElement("p");
    description.className =
      "small text-muted line-clamp-2 mb-3 flex-grow-1";
    description.textContent = item.description || "Pilihan menu spesial";
    const footer = document.createElement("div");
    footer.className =
      "d-flex align-items-center justify-content-between mt-auto gap-1";
    const price = document.createElement("span");
    price.className = "fw-bold text-dark small";
    price.textContent = money(item.price);
    const add = document.createElement("button");
    add.type = "button";
    add.className = "btn btn-sm btn-primary-app rounded-pill px-2.5 py-1";
    add.dataset.menuId = item.id;
    add.textContent = "+ Tambah";

    footer.append(price, add);
    body.append(category, name, description, footer);
    card.append(cover, body);
    column.append(card);
    grid.append(column);
  });
}

function renderCategories() {
  const categories = ["Semua", ...new Set(state.menu.map((item) => item.category))];
  const container = document.querySelector("#categories");
  container.replaceChildren();

  categories.forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      "btn category-chip rounded-pill px-3 py-1.5 small" +
      (category === state.category ? " active" : "");
    button.dataset.category = category;
    button.textContent = category;
    container.append(button);
  });
}

function openItem(id) {
  state.chosen = state.menu.find((item) => item.id === id);
  if (!state.chosen) {
    return;
  }
  document.querySelector("#modalTitle").textContent = state.chosen.name;
  document.querySelector("#modalPrice").textContent =
    `Mulai ${money(state.chosen.price)}`;

  const body = document.querySelector("#modalBody");
  body.replaceChildren();
  state.chosen.variants.forEach((group) => {
    const section = document.createElement("div");
    section.className = "mb-3";
    const title = document.createElement("label");
    title.className = "form-label fw-semibold small";
    title.textContent = group.name + (group.required ? " *" : "");
    section.append(title);

    group.options.forEach((option) => {
      const row = document.createElement("div");
      row.className = "form-check";
      const input = document.createElement("input");
      input.className = "form-check-input variant-choice";
      input.type = "radio";
      input.name = `group-${group.id}`;
      input.value = option.id;
      input.required = group.required;
      const label = document.createElement("label");
      label.className = "form-check-label small";
      label.textContent =
        `${option.name} ` +
        (Number(option.price_adjustment)
          ? `+${money(option.price_adjustment)}`
          : "");
      row.append(input, label);
      section.append(row);
    });
    body.append(section);
  });

  if (state.chosen.addons.length) {
    const section = document.createElement("div");
    section.className = "mb-3";
    const title = document.createElement("label");
    title.className = "form-label fw-semibold small";
    title.textContent = "Tambahan";
    section.append(title);
    state.chosen.addons.forEach((addon) => {
      const row = document.createElement("div");
      row.className = "form-check";
      const input = document.createElement("input");
      input.className = "form-check-input addon-choice";
      input.type = "checkbox";
      input.value = addon.id;
      const label = document.createElement("label");
      label.className = "form-check-label small";
      label.textContent = `${addon.name} +${money(addon.price)}`;
      row.append(input, label);
      section.append(row);
    });
    body.append(section);
  }

  const quantityLabel = document.createElement("label");
  quantityLabel.className = "form-label fw-semibold small mt-1";
  quantityLabel.htmlFor = "itemQty";
  quantityLabel.textContent = "Jumlah";
  const quantity = document.createElement("input");
  quantity.id = "itemQty";
  quantity.className = "form-control";
  quantity.type = "number";
  quantity.min = "1";
  quantity.value = "1";
  body.append(quantityLabel, quantity);

  bootstrap.Modal.getOrCreateInstance(
    document.querySelector("#itemModal"),
  ).show();
}

export function bindMenu() {
  document.querySelector("#search").addEventListener("input", renderMenu);
  document.querySelector("#categories").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-category]");
    if (!button) {
      return;
    }
    state.category = button.dataset.category;
    renderCategories();
    renderMenu();
  });
  document.querySelector("#menuGrid").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-menu-id]");
    if (button) {
      openItem(Number(button.dataset.menuId));
    }
  });
}

export function renderCatalog() {
  renderCategories();
  renderMenu();
}
