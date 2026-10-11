import { money } from "./api.mjs";
import { state } from "./state.mjs";

function menuImage(item) { return item.image_url || ""; }

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
    card.className = "card menu-card h-100 bg-white";
    const cover = document.createElement("div");
    cover.className = "food-cover mb-2";
    const image = document.createElement("img");
    if (menuImage(item)) {
      const image = document.createElement("img");
      image.src = menuImage(item);
      image.alt = item.name;
      image.loading = "lazy";
      image.width = 400;
      image.height = 300;
      image.addEventListener("error", () => {
        cover.replaceChildren();
        cover.innerHTML = `<span class="food-placeholder">${item.name.charAt(0).toUpperCase()}</span>`;
      }, { once: true });
      cover.append(image);
    } else {
      cover.innerHTML = `<span class="food-placeholder">${item.name.charAt(0).toUpperCase()}</span>`;
    }

    const body = document.createElement("div");
    body.className = "card-body p-1 d-flex flex-column";
    const tags = document.createElement("div");
    tags.className = "d-flex gap-1 flex-wrap mb-2";
    (item.tags || []).slice(0, 2).forEach((tag) => {
      const chip = document.createElement("span");
      chip.className = "badge bg-light text-secondary border fw-normal";
      chip.textContent = tag;
      tags.append(chip);
    });
    const name = document.createElement("h3");
    name.className = "h6 fw-bold mb-1 text-truncate";
    name.textContent = item.name;
    const description = document.createElement("p");
    description.className =
      "small text-muted line-clamp-2 mb-3 flex-grow-1";
    description.textContent = item.description || "Dibuat segar untukmu hari ini.";
    const footer = document.createElement("div");
    footer.className =
      "d-flex align-items-center justify-content-between mt-auto gap-1";
    const price = document.createElement("span");
    price.className = "fw-bold text-dark";
    price.textContent = money(item.price);
    const add = document.createElement("button");
    add.type = "button";
    add.className = "btn btn-primary-app rounded-circle menu-add d-flex align-items-center justify-content-center";
    add.dataset.menuId = item.id;
    add.textContent = "+";

    footer.append(price, add);
    body.append(tags, name, description, footer);
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
  document.querySelector("#modalDescription").textContent = state.chosen.description || "";
  const modalImage = document.querySelector("#modalImage");
  modalImage.replaceChildren();
  if (state.chosen.image_url) {
    const image = document.createElement("img");
    image.src = state.chosen.image_url;
    image.alt = state.chosen.name;
    image.className = "w-100 h-100 object-fit-cover rounded-3";
    image.onerror = () => modalImage.innerHTML = `<span class="food-placeholder">${state.chosen.name.charAt(0)}</span>`;
    modalImage.append(image);
  } else {
    modalImage.innerHTML = `<span class="food-placeholder">${state.chosen.name.charAt(0)}</span>`;
  }

  const body = document.querySelector("#modalBody");
  body.replaceChildren();
  state.chosen.variants.forEach((group) => {
    const section = document.createElement("div");
    section.className = "mb-3";
    const title = document.createElement("label");
    title.className = "form-label fw-semibold small d-flex align-items-center gap-2";
    title.innerHTML = `${group.name} <span class="badge ${group.required ? "bg-success-subtle text-success" : "bg-light text-secondary"}">${group.required ? "Wajib" : "Opsional"}</span>`;
    section.append(title);

    group.options.forEach((option) => {
      const row = document.createElement("div");
      row.className = "option-row mb-2 d-flex align-items-center gap-2";
      const input = document.createElement("input");
      input.className = "form-check-input variant-choice";
      input.type = "radio";
      input.name = `group-${group.id}`;
      input.value = option.id;
      input.required = group.required;
      input.checked = group.required && group.options[0].id === option.id;
      input.dataset.price = option.price_adjustment;
      const label = document.createElement("label");
      label.className = "form-check-label small";
      label.textContent =
        `${option.name} ` +
        (Number(option.price_adjustment)
          ? `+${money(option.price_adjustment)}`
          : "");
      row.append(input, label);
      row.addEventListener("click", (event) => {
        if (event.target !== input) {
          input.click();
        }
      });
      section.append(row);
    });
    if (group.required) {
      section.querySelector(".variant-choice").checked = true;
    }
    body.append(section);
  });

  if (state.chosen.addons.length) {
    const section = document.createElement("div");
    section.className = "mb-3";
    const title = document.createElement("label");
    title.className = "form-label fw-semibold small d-flex align-items-center gap-2";
    title.innerHTML = 'Tambahan <span class="badge bg-light text-secondary">Opsional</span>';
    section.append(title);
    state.chosen.addons.forEach((addon) => {
      const row = document.createElement("div");
      row.className = "option-row mb-2 d-flex align-items-center gap-2";
      const input = document.createElement("input");
      input.className = "form-check-input addon-choice";
      input.type = "checkbox";
      input.value = addon.id;
      input.dataset.price = addon.price;
      const label = document.createElement("label");
      label.className = "form-check-label small";
      label.textContent = `${addon.name} +${money(addon.price)}`;
      row.append(input, label);
      row.addEventListener("click", (event) => {
        if (event.target !== input) {
          input.click();
        }
      });
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
  quantity.className = "form-control text-center";
  body.append(quantityLabel, quantity);
  const total = document.createElement("div");
  total.className = "text-end text-secondary small mt-3";
  body.append(total);
  const updateTotal = () => {
    const variantTotal = [...body.querySelectorAll(".variant-choice:checked")]
      .reduce((sum, input) => sum + Number(input.dataset.price || 0), 0);
    const addonTotal = [...body.querySelectorAll(".addon-choice:checked")]
      .reduce((sum, input) => sum + Number(input.dataset.price || 0), 0);
    const value = (Number(state.chosen.price) + variantTotal + addonTotal) * Number(quantity.value || 1);
    total.textContent = `Total ${money(value)}`;
    document.querySelector("#confirmAdd").textContent = `Tambahkan · ${money(value)}`;
  };
  body.querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", updateTotal);
  });
  quantity.addEventListener("input", updateTotal);
  updateTotal();

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
