import { api } from "./api.mjs";
import { bindCart, refreshCart } from "./cart.mjs";
import { bindCheckout } from "./checkout.mjs";
import { bindMenu, renderCatalog } from "./menu.mjs";
import { bindTableScanner, establishTableContext } from "./table-scanner.mjs";
import { state } from "./state.mjs";

async function initializeStorefront() {
  bindMenu();
  bindCart();
  bindCheckout();
  bindTableScanner();

  try {
    await establishTableContext();
    const response = await api("/api/menu/");
    state.menu = response.items;
    renderCatalog();
    await refreshCart();
  } catch (error) {
    console.error("Initialization error:", error);
    const grid = document.querySelector("#menuGrid");
    const alert = document.createElement("div");
    alert.className = "col-12";
    const message = document.createElement("div");
    message.className = "alert alert-danger";
    message.textContent = "Gagal memuat menu. Silakan muat ulang halaman.";
    alert.append(message);
    grid.replaceChildren(alert);
  }
}

initializeStorefront();
