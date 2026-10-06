import { api, toast } from "./api.mjs";
import { state } from "./state.mjs";
import { renderOrderType } from "./table-scanner.mjs";

function openCheckout() {
  const cartDrawer = document.querySelector("#cartDrawer");
  const drawer = bootstrap.Offcanvas.getInstance(cartDrawer);
  if (drawer) {
    drawer.hide();
  }
  renderOrderType();
  bootstrap.Modal.getOrCreateInstance(
    document.querySelector("#checkoutModal"),
  ).show();
}

async function submitCheckout(event) {
  event.preventDefault();
  const formData = Object.fromEntries(new FormData(event.target));
  const errorMessage = document.querySelector("#checkoutError");
  errorMessage.classList.add("d-none");

  if (formData.order_type === "DINE_IN" && !state.tableContext) {
    errorMessage.textContent = "Mohon pindai QR meja terlebih dahulu.";
    errorMessage.classList.remove("d-none");
    return;
  }

  const payload = {
    ...formData,
    table_token:
      formData.order_type === "DINE_IN" ? state.tableContext?.token : null,
  };

  try {
    const result = await api("/api/orders/checkout/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    bootstrap.Modal.getInstance(
      document.querySelector("#checkoutModal"),
    ).hide();
    toast("Pesanan berhasil dibuat!");
    window.location.href = `/orders/${result.public_id}/`;
  } catch (error) {
    errorMessage.textContent = error.message;
    errorMessage.classList.remove("d-none");
  }
}

export function bindCheckout() {
  document
    .querySelector("#checkoutButton")
    .addEventListener("click", openCheckout);
  document
    .querySelector("#checkoutForm")
    .addEventListener("submit", submitCheckout);
}
