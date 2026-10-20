// Measure real footer/visible viewport sizes instead of assuming one phone size.
const root = document.documentElement;
const viewport = window.visualViewport;
function updateViewport() {
  // Preserve browser zoom; only follow the unzoomed viewport/keyboard height.
  if (!viewport || Math.abs(viewport.scale - 1) < 0.01) {
    root.style.setProperty("--app-height", `${Math.round(viewport?.height ?? window.innerHeight)}px`);
  }
}
updateViewport();
viewport?.addEventListener("resize", updateViewport);
window.addEventListener("resize", updateViewport);
window.addEventListener("pageshow", updateViewport);

const menu = document.querySelector("#menuView");
const cart = document.querySelector("#floatingCart");
if (menu && cart) {
  const updateCart = () => menu.style.setProperty(
    "--cart-bar-height", `${Math.ceil(cart.getBoundingClientRect().height)}px`,
  );
  new ResizeObserver(updateCart).observe(cart);
  updateCart();
}
