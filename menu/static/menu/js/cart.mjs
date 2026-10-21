import { createFoodVisual } from './menu-card.mjs?v=customer-p4-r5';
import { api, money, toast } from "./api.mjs?v=customer-p4-r5";
import { state } from "./state.mjs?v=customer-p4-r5";
import { openItem } from "./menu.mjs?v=customer-p4-r5";

let pendingNoteSave = Promise.resolve(true);
export async function flushCartNotes() {
  const saved = await pendingNoteSave;
  if (!saved) pendingNoteSave = Promise.resolve(true);
  return saved;
}

function createCartItem(item) {
  const card = document.createElement("div");
  card.className = "cart-item-card";

  const heading = document.createElement("div");
  heading.className =
    "d-flex justify-content-between align-items-start gap-2 mb-1.5";
  const itemInfo = document.createElement("div");
  itemInfo.className = "d-flex align-items-center gap-2";
  const icon = createFoodVisual(item, { eager: true });
  icon.classList.add("cart-item-image");
  const details = document.createElement("div");
  details.className = "cart-item-details";
  const name = document.createElement("h6");
  name.className = "fw-bold text-dark m-0 fs-6";
  name.textContent = item.name;
  const variants = [
    ...item.variants.map((variant) => variant.name),
    ...item.addons.map((addon) => `Tambah ${addon.name.toLowerCase()}`),
  ].join(" · ");
  const selection = document.createElement("div");
  selection.className = variants
    ? "mt-1 badge bg-white text-secondary border fw-normal px-2 py-0.5 rounded-pill small"
    : "small text-muted";
  selection.textContent = variants || "Tanpa tambahan";
  const price = document.createElement("strong");
  price.className = "accent cart-line-price";
  price.textContent = money(item.line_total);
  details.append(name, selection, price);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className =
    "btn btn-sm text-danger rounded-circle border-0 d-inline-flex align-items-center justify-content-center";
  remove.style.width = "32px";
  remove.style.height = "32px";
  remove.setAttribute("aria-label", `Hapus ${item.name}`);
  remove.dataset.cartAction = "remove";
  remove.dataset.lineId = item.id;
  remove.textContent = "";
  remove.classList.add("remove-line");
  itemInfo.append(icon, details);
  heading.append(itemInfo, remove);

  const footer = document.createElement("div");
  footer.className =
    "d-flex align-items-center justify-content-between mt-3 pt-2 border-top border-light-subtle";
  const lineTotal = document.createElement("span");
  lineTotal.className = "fw-bold text-success fs-6";
  lineTotal.textContent = money(item.line_total);
  const stepper = document.createElement("div");
  stepper.className =
    "capsule-stepper rounded-pill d-inline-flex align-items-center shadow-sm";
  const decrement = document.createElement("button");
  decrement.type = "button";
  decrement.className =
    "btn btn-sm stepper-btn rounded-circle d-flex align-items-center justify-content-center p-0";
  decrement.dataset.cartAction = "quantity";
  decrement.dataset.lineId = item.id;
  decrement.dataset.quantity = item.quantity - 1;
  decrement.setAttribute("aria-label", `Kurangi jumlah ${item.name}`);
  decrement.textContent = "−";
  decrement.disabled = item.quantity <= 1;
  const quantity = document.createElement("span");
  quantity.className = "px-2.5 fw-bold small text-dark";
  quantity.textContent = item.quantity;
  const increment = document.createElement("button");
  increment.type = "button";
  increment.className = decrement.className;
  increment.dataset.cartAction = "quantity";
  increment.dataset.lineId = item.id;
  increment.dataset.quantity = item.quantity + 1;
  increment.setAttribute("aria-label", `Tambah jumlah ${item.name}`);
  increment.textContent = "+";

  stepper.append(decrement, quantity, increment);
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "edit-selection";
  edit.textContent = "Edit pilihan";
  edit.dataset.cartAction = "edit";
  edit.dataset.lineId = item.id;
  footer.append(edit, stepper);
  card.append(heading);
  const noteBar = document.createElement("label");
  noteBar.className = "cart-kitchen-note";
  const note = document.createElement("input");
  note.type = "text";
  note.maxLength = 500;
  note.value = item.note || "";
  note.placeholder = "Tambah catatan untuk dapur…";
  note.setAttribute("aria-label", `Catatan untuk ${item.name}`);
  const noteStatus = document.createElement("span");
  noteStatus.className = "visually-hidden";
  noteStatus.setAttribute("role", "status");
  note.addEventListener("change", () => {
    const value = note.value.trim();
    if (value === (item.note || "")) return;
    note.readOnly = true;
    noteBar.setAttribute("aria-busy", "true");
    noteStatus.textContent = "Menyimpan catatan…";
    pendingNoteSave = pendingNoteSave.then(async () => {
      try {
        const current = state.cart.items.find(line => line.id === item.id);
        if (!current) return false;
        state.cart = await api(`/api/cart/${item.id}/`, {method:"PATCH", keepalive:true, body:JSON.stringify({
          quantity:current.quantity, variant_ids:current.variants.map(option=>option.id),
          addon_ids:current.addons.map(option=>option.id), note:value,
        })});
        item.note = value;
        note.value = value;
        noteStatus.textContent = "Catatan tersimpan";
        return true;
      } catch(error) {
        note.value = item.note || "";
        noteStatus.textContent = "Catatan gagal disimpan";
        toast(error.message);
        return false;
      } finally {
        note.readOnly = false;
        noteBar.setAttribute("aria-busy", "false");
        document.querySelector("#checkoutButton").disabled = !state.cart.items.length;
      }
    });
  });
  noteBar.append(note, noteStatus);
  card.append(noteBar);
  card.append(footer);
  return card;
}

export async function refreshCart() {
  state.cart = await api("/api/cart/");
  const count = state.cart.items.reduce((total, item) => total + item.quantity, 0);
  document.querySelector("#floatingCart").classList.toggle("d-none", count === 0);
  document.querySelector("#cartCount").textContent = "Item";
  document.querySelector("#floatingCount").textContent = count;
  document.querySelector("#drawerSubtotalLabel").textContent = `Subtotal (${count} porsi)`;
  const addons = [...new Set(state.cart.items.flatMap(item=>item.addons.map(addon=>addon.name.toLowerCase())))];
  document.querySelector("#drawerAddonsLabel").textContent = addons.length ? `Tambahan ${addons.join(", ")}` : "Tambahan";
  document.querySelector("#drawerItemCount").textContent = `· ${count} item`;
  document.querySelector("#cartTotal").textContent = money(state.cart.total);
  document.querySelector("#drawerTotal").textContent = money(state.cart.total);
  document.querySelector("#drawerSubtotal").textContent = money(state.cart.total);
  document.querySelector("#summaryTotal").textContent = money(state.cart.total);
  document.querySelector("#headerCartCount").textContent = count;
  document.querySelector("#headerCartCount").classList.toggle("d-none", count === 0);
  document.querySelector("#checkoutButton").disabled = count === 0;

  const lines = document.querySelector("#cartLines");
  lines.replaceChildren();
  if (!state.cart.items.length) {
    const empty = document.createElement("div");
    empty.className = "text-center py-5";
    const title = document.createElement("h6");
    title.className = "fw-bold text-dark mb-1";
    title.textContent = "Keranjangmu Masih Kosong";
    const description = document.createElement("p");
    description.className = "small text-muted mb-4";
    description.textContent = "Yuk, pilih menu favoritmu terlebih dahulu!";
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className =
      "btn btn-outline-secondary rounded-pill btn-sm px-4";
    dismiss.dataset.bsDismiss = "offcanvas";
    dismiss.textContent = "Mulai Pilih Menu";
    empty.append(title, description, dismiss);
    lines.append(empty);
    return;
  }

  state.cart.items.forEach((item) => lines.append(createCartItem(item)));
}

async function changeQuantity(id, quantity) {
  if (!await flushCartNotes()) return;
  try {
    await api(`/api/cart/${id}/`, {
      method: "PATCH",
      body: JSON.stringify({ quantity }),
    });
    await refreshCart();
  } catch (error) {
    toast(error.message);
  }
}

async function removeLine(id) {
  if (!await flushCartNotes()) return;
  try {
    await api(`/api/cart/${id}/`, { method: "DELETE" });
    await refreshCart();
  } catch (error) {
    toast(error.message);
  }
}

async function addChosenItem() {
  const form = document.querySelector("#modalBody");
  const invalid = form.querySelector("input:invalid");
  if (invalid && !invalid.reportValidity()) {
    return;
  }

  try {
    document.querySelector("#confirmAdd").disabled = true;
    await api(state.editingLine ? `/api/cart/${state.editingLine}/` : "/api/cart/add/", {
      method: state.editingLine ? "PATCH" : "POST",
      body: JSON.stringify({
        menu_item_id: state.chosen.id,
        note: document.querySelector("#itemNote").value,
        quantity: Number(document.querySelector("#itemQty").value),
        variant_ids: [
          ...form.querySelectorAll(".variant-choice:checked"),
        ].map((input) => Number(input.value)),
        addon_ids: [
          ...form.querySelectorAll(".addon-choice:checked"),
        ].map((input) => Number(input.value)),
      }),
    });
    bootstrap.Modal.getInstance(document.querySelector("#itemModal")).hide();
    await refreshCart();
    toast(state.editingLine ? "Pilihan disimpan" : "Ditambahkan ke keranjang");
  } catch (error) {
    toast(error.message);
  } finally {
    document.querySelector("#confirmAdd").disabled = false;
  }
}

export function bindCart() {
  document.querySelector("#confirmAdd").addEventListener("click", addChosenItem);
  document.querySelector("#cartLines").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-cart-action]");
    if (!button) {
      return;
    }
    if (button.dataset.cartAction === "edit") {
      if (!await flushCartNotes()) return;
      const line = state.cart.items.find(item => item.id === button.dataset.lineId);
      const drawer = document.querySelector("#cartDrawer");
      drawer.addEventListener("hidden.bs.offcanvas", () => openItem(line.menu_item_id, line), {once:true});
      bootstrap.Offcanvas.getInstance(drawer).hide();
    } else if (button.dataset.cartAction === "remove") {
      removeLine(button.dataset.lineId);
    } else {
      changeQuantity(button.dataset.lineId, Number(button.dataset.quantity));
    }
  });
}
