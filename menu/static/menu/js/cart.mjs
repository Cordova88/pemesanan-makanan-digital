import { api, money, toast } from "./api.mjs";
import { state } from "./state.mjs";

function createCartItem(item) {
  const card = document.createElement("div");
  card.className = "cart-item-card p-3 mb-2.5";

  const heading = document.createElement("div");
  heading.className =
    "d-flex justify-content-between align-items-start gap-2 mb-1.5";
  const itemInfo = document.createElement("div");
  itemInfo.className = "d-flex align-items-center gap-2";
  const icon = document.createElement("div");
  icon.className =
    "bg-white rounded-3 d-flex align-items-center justify-content-center border flex-shrink-0";
  icon.style.cssText = "width:32px;height:32px;color:#94a3b8";
  icon.textContent = "▧";
  const details = document.createElement("div");
  const name = document.createElement("h6");
  name.className = "fw-bold text-dark m-0 fs-6";
  name.textContent = item.name;
  const variants = [
    ...item.variants.map((variant) => variant.name),
    ...item.addons.map((addon) => addon.name),
  ].join(" · ");
  const selection = document.createElement("div");
  selection.className = variants
    ? "mt-1 badge bg-white text-secondary border fw-normal px-2 py-0.5 rounded-pill small"
    : "small text-muted";
  selection.textContent = variants || "Tanpa tambahan";
  details.append(name, selection);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className =
    "btn btn-sm text-danger bg-danger-subtle rounded-pill px-2.5 py-1 border-0 d-inline-flex align-items-center gap-1";
  remove.setAttribute("aria-label", `Hapus ${item.name}`);
  remove.dataset.cartAction = "remove";
  remove.dataset.lineId = item.id;
  remove.textContent = "Hapus";
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
  decrement.textContent = item.quantity === 1 ? "×" : "−";
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
  footer.append(lineTotal, stepper);
  card.append(heading, footer);
  return card;
}

export async function refreshCart() {
  state.cart = await api("/api/cart/");
  const count = state.cart.items.reduce((total, item) => total + item.quantity, 0);
  document.querySelector("#floatingCart").classList.toggle("d-none", count === 0);
  document.querySelector("#cartCount").textContent = `${count} Item`;
  document.querySelector("#drawerItemCount").textContent = `· ${count} item`;
  document.querySelector("#cartTotal").textContent = money(state.cart.total);
  document.querySelector("#drawerTotal").textContent = money(state.cart.total);
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
    await api("/api/cart/add/", {
      method: "POST",
      body: JSON.stringify({
        menu_item_id: state.chosen.id,
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
    toast("Ditambahkan ke keranjang");
  } catch (error) {
    toast(error.message);
  }
}

export function bindCart() {
  document.querySelector("#confirmAdd").addEventListener("click", addChosenItem);
  document.querySelector("#cartLines").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-cart-action]");
    if (!button) {
      return;
    }
    if (button.dataset.cartAction === "remove") {
      removeLine(button.dataset.lineId);
    } else {
      changeQuantity(button.dataset.lineId, Number(button.dataset.quantity));
    }
  });
}
