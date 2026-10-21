import { createMenuCard, createFoodVisual, createDetailPhoto } from './menu-card.mjs?v=customer-p4-r5';
import { money } from "./api.mjs?v=customer-p4-r5";
import { state } from "./state.mjs?v=customer-p4-r5";

function renderMenu() {
  const query = document.querySelector("#search").value.toLowerCase();
  const filtered = state.menu.filter(
    (item) =>
      (state.category === "Semua" || item.category === state.category) &&
      item.name.toLowerCase().includes(query),
  );
  const grid = document.querySelector("#menuGrid");
  document.querySelector("#menuCount").textContent = `${filtered.length} Menu`;
  grid.replaceChildren();

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "col-12 text-center py-5 text-secondary";
    empty.textContent = "Menu tidak ditemukan.";
    grid.append(empty);
    return;
  }

  filtered.forEach((item, index) => {
    const column = document.createElement("div");
    column.className = "col-6";
    column.append(createMenuCard(item, { eager: index < 2 }));
    grid.append(column);
  });
}

function renderCategories() {
  const available = [...new Set(state.menu.map(item => item.category))];
  const categories = ["Semua", ...["Makanan","Minuman","Camilan"].filter(name=>available.includes(name)), ...available.filter(name=>!["Makanan","Minuman","Camilan"].includes(name))];
  const container = document.querySelector("#categories");
  container.replaceChildren();

  categories.forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      "category-chip" +
      (category === state.category ? " active" : "");
    button.setAttribute("aria-pressed", String(category === state.category));
    button.dataset.category = category;
    button.textContent = category;
    container.append(button);
  });
}

export function openItem(id, line = null) {
  state.editingLine = line?.id || null;
  state.chosen = state.menu.find((item) => item.id === id);
  if (!state.chosen) {
    return;
  }
  document.querySelector("#modalTitle").textContent = state.chosen.name;
  document.querySelector("#itemBasePrice").textContent = money(state.chosen.price);
  document.querySelector("#modalDescription").textContent = state.chosen.description || "";
  const modalImage = document.querySelector("#modalImage");
  modalImage.replaceChildren();
  modalImage.append(createDetailPhoto(state.chosen));

  const body = document.querySelector("#modalBody");
  body.replaceChildren();
  state.chosen.variants.forEach((group) => {
    const section = document.createElement("div");
    section.className = "choice-section mb-3";
    const title = document.createElement("label");
    title.className = "form-label fw-semibold small d-flex align-items-center gap-2";
    title.textContent = group.name;
    const requirement = document.createElement("span");
    requirement.className = `badge ${group.required ? "bg-success-subtle text-success" : "bg-light text-secondary"}`;
    requirement.textContent = group.required ? "Wajib pilih" : "Opsional";
    title.append(requirement);
    section.append(title);

    const chips = document.createElement("div");
    chips.className = "variant-chips";
    group.options.forEach((option) => {
      const row = document.createElement("div");
      row.className = "option-row mb-2 d-flex align-items-center gap-2";
      const input = document.createElement("input");
      input.className = "form-check-input variant-choice";
      input.type = "radio";
      input.name = `group-${group.id}`;
      input.value = option.id;
      input.required = group.required;
      input.setAttribute("aria-label", option.name);
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
      chips.append(row);
    });
    section.append(chips);
    if (group.required) {
      section.querySelector(".variant-choice").checked = true;
    }
    body.append(section);
  });

  if (state.chosen.addons.length) {
    const section = document.createElement("div");
    section.className = "choice-section mb-3";
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
      input.setAttribute("aria-label", addon.name);
      input.dataset.price = addon.price;
      const label = document.createElement("label");
      label.className = "form-check-label small";
      const addonName = document.createElement("span");
      addonName.textContent = addon.name;
      const addonPrice = document.createElement("strong");
      addonPrice.className = "accent";
      addonPrice.textContent = `+${money(addon.price)}`;
      label.append(addonName, addonPrice);
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

  const noteLabel = document.createElement("label");
  noteLabel.className = "form-label kitchen-label";
  noteLabel.htmlFor = "itemNote";
  noteLabel.textContent = "Catatan untuk dapur (opsional)";
  const note = document.createElement("textarea");
  note.id = "itemNote";
  note.className = "form-control kitchen-note";
  note.maxLength = 500;
  note.rows = 2;
  note.placeholder = "Sambal dipisah, ya.";
  note.value = line?.note || "";
  const row = document.createElement("div");
  row.className = "item-quantity-row";
  const stepper = document.createElement("div");
  stepper.className = "item-stepper";
  const quantity = document.createElement("input");
  quantity.id = "itemQty";
  quantity.type = "number";
  quantity.min = "1";
  quantity.step = "1";
  quantity.max = "99";
  quantity.value = line?.quantity || 1;
  quantity.setAttribute("aria-label", "Jumlah porsi");
  const less = document.createElement("button"), more = document.createElement("button");
  less.type = more.type = "button";
  less.textContent = "−"; more.textContent = "+";
  less.setAttribute("aria-label","Kurangi porsi"); more.setAttribute("aria-label","Tambah porsi");
  stepper.append(less,quantity,more);
  const total = document.createElement("strong");
  total.className = "accent item-total";
  row.append(stepper, total);
  body.append(noteLabel,note,row);
  if (line) {
    body.querySelectorAll(".variant-choice").forEach(input => input.checked = line.variant_ids.includes(Number(input.value)));
    body.querySelectorAll(".addon-choice").forEach(input => input.checked = line.addon_ids.includes(Number(input.value)));
  }
  const updateTotal = () => {
    const count = Number(quantity.value);
    const extra = [...body.querySelectorAll("input:checked")].reduce((sum,input)=>sum+Number(input.dataset.price||0),0);
    const value = (Number(state.chosen.price)+extra) * (Number.isFinite(count) ? count : 0);
    total.textContent = money(value);
    less.disabled = count <= 1;
    more.disabled = count >= 99;
    document.querySelector("#itemFooterTotal").textContent = `${count || 0} porsi · Total ${money(value)}`;
    document.querySelector("#confirmAdd").textContent = line ? "Simpan pilihan" : "Tambah ke keranjang";
  };
  less.onclick = () => { quantity.value = Math.max(1,Number(quantity.value)-1); updateTotal(); };
  more.onclick = () => { quantity.value = Math.min(99,Number(quantity.value)+1); updateTotal(); };
  body.onchange = updateTotal;
  quantity.addEventListener("input",updateTotal);
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
  const hero = document.querySelector('#homeHero');
  const featured = state.menu.find(item => item.image_url) || state.menu[0];
  hero.replaceChildren();
  if (featured) hero.append(createFoodVisual(featured, { eager: true }));
  const favorites = document.querySelector("#homeFavorites");
  favorites.replaceChildren();
  state.menu.slice(0, 2).forEach((item) => {
    const card = document.createElement("a");
    card.href = "#menu";
    card.addEventListener("click", () => openItem(item.id));
    card.className = "favorite-card";
    const image = createFoodVisual(item);
    const name = document.createElement("strong");
    name.textContent = item.name;
    card.append(image, name);
    favorites.append(card);
  });
  if (!state.menu.length) favorites.textContent = "Menu belum tersedia.";
}
