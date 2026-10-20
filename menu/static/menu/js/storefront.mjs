import { api } from "./api.mjs?v=images-p8";
import { bindCart, refreshCart } from "./cart.mjs?v=images-p8";
import { bindCheckout } from "./checkout.mjs?v=images-p8";
import { bindMenu, renderCatalog } from "./menu.mjs?v=images-p8";
import { bindTableScanner, establishTableContext } from "./table-scanner.mjs?v=images-p8";
import { state } from "./state.mjs?v=images-p8";
import { bindCustomerNavigation } from "./navigation.mjs?v=images-p8";

function showView() {
  const showMenu = ["#menu", "#pilihan-menu", "#keranjang", "#konfirmasi", "#jenis-pesanan"].includes(window.location.hash) || new URLSearchParams(window.location.search).has("menu");
  document.querySelector("#homeView").classList.toggle("d-none", showMenu);
  document.querySelector("#menuView").classList.toggle("d-none", !showMenu);
  window.scrollTo(0, 0);
}

export function updateServiceContext() {
  const dineIn = document.querySelector("#orderType").value === "DINE_IN";
  document.body.classList.toggle("dine-in", dineIn);
  document.querySelector("#serviceLabel").textContent = dineIn ? "Makan di tempat" : "Bawa pulang";
  document.querySelector("#serviceDetail").textContent = dineIn && state.tableContext
    ? `Meja ${state.tableContext.number} · RasaKita`
    : dineIn ? "Pindai QR meja saat konfirmasi" : "RasaKita · Pesanan untuk dibawa";
  document.querySelectorAll(".cart-service-label").forEach(el=>el.textContent=document.querySelector("#serviceLabel").textContent);
  document.querySelectorAll(".cart-service-detail").forEach(el=>el.textContent=document.querySelector("#serviceDetail").textContent);
}

async function initializeStorefront() {
  bindCustomerNavigation();
  bindMenu();
  document.querySelector(".cart-service").addEventListener("click",()=>{
    const drawer=document.querySelector("#cartDrawer");
    drawer.addEventListener("hidden.bs.offcanvas",()=>bootstrap.Modal.getOrCreateInstance(document.querySelector("#serviceModal")).show(),{once:true});
    bootstrap.Offcanvas.getInstance(drawer).hide();
  });
  bindCart();
  bindCheckout();
  bindTableScanner();
  showView();
  window.addEventListener("hashchange", showView);
  window.addEventListener("customer:navigation", showView);
  document.querySelectorAll("[data-service]").forEach(button => button.addEventListener("click", () => {
    document.querySelector("#orderType").value = button.dataset.service;
    updateServiceContext();
    bootstrap.Modal.getInstance(document.querySelector("#serviceModal")).hide();
  }));
  document.querySelector("#orderType").addEventListener("change", updateServiceContext);
  document.querySelector("#checkoutModal").addEventListener("hidden.bs.modal", updateServiceContext);

  try {
    await establishTableContext();
    if (state.tableContext) {
      document.querySelector("#orderType").value = "DINE_IN";

    }
    updateServiceContext();
    const response = await api("/api/menu/");
    state.menu = response.items;
    renderCatalog();
    const selectedId = Number(new URLSearchParams(window.location.search).get("menu"));
    if (selectedId) { const {openItem}=await import("./menu.mjs?v=images-p8"); openItem(selectedId); }
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
    document.querySelector("#homeFavorites").textContent = "Menu belum dapat dimuat. Buka menu untuk mencoba kembali.";
  }
}

initializeStorefront();
