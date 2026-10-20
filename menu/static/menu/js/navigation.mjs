// Keep browser Back/Forward consistent with customer screens.
export function bindCustomerNavigation() {
  const screens = [
    ["itemModal", "modal", "pilihan-menu"],
    ["cartDrawer", "offcanvas", "keranjang"],
    ["checkoutModal", "modal", "konfirmasi"],
    ["serviceModal", "modal", "jenis-pesanan"],
  ];
  let replaying = false;
  const opening = new Set();
  if (!history.state?.customerScreen) {
    history.replaceState({customerScreen: location.hash && location.hash !== "#beranda" ? "menu" : "home"}, "", location.href);
  }
  for (const [id, kind, route] of screens) {
    const element = document.getElementById(id);
    element.addEventListener(`shown.bs.${kind}`, () => opening.delete(id));
    element.addEventListener(`show.bs.${kind}`, () => {
      opening.add(id);
      if (!replaying && history.state?.customerScreen !== id) {
        history.pushState({customerScreen: id}, "", `#${route}`);
        window.dispatchEvent(new Event("customer:navigation"));
      }
    });
    element.addEventListener(`hidden.bs.${kind}`, () => {
      if (!replaying && history.state?.customerScreen === id) {
        history.replaceState({customerScreen: "menu"}, "", "#menu");
        window.dispatchEvent(new Event("customer:navigation"));
      }
    });
  }
  window.addEventListener("popstate", async event => {
    if (replaying) return;
    replaying = true;
    const target = event.state?.customerScreen;
    const closing = [];
    for (const [id, kind] of screens) {
      const element = document.getElementById(id);
      if (id !== target && opening.has(id)) {
        await new Promise(resolve => element.addEventListener(`shown.bs.${kind}`, resolve, {once: true}));
      }
      if (element.classList.contains("show") && id !== target) {
        closing.push(new Promise(resolve => element.addEventListener(`hidden.bs.${kind}`, resolve, {once: true})));
        (kind === "modal" ? bootstrap.Modal : bootstrap.Offcanvas).getInstance(element)?.hide();
      }
    }
    await Promise.all(closing);
    const entry = screens.find(([id]) => id === target);
    if (entry) {
      const [id, kind] = entry;
      (kind === "modal" ? bootstrap.Modal : bootstrap.Offcanvas).getOrCreateInstance(document.getElementById(id)).show();
    }
    replaying = false;
  });
}
