// Keep browser Back/Forward consistent with customer screens.
export function bindCustomerNavigation() {
  const screens = [
    ["itemModal", "modal", "pilihan-menu"],
    ["cartDrawer", "offcanvas", "keranjang"],
    ["checkoutModal", "modal", "konfirmasi"],
    ["serviceModal", "modal", "jenis-pesanan"],
  ];
  let replaying = false;
  let serviceFromCart = false;
  let guardCartFocus = false;
  const opening = new Set();
  if (!history.state?.customerScreen) {
    history.replaceState({customerScreen: location.hash && location.hash !== "#beranda" ? "menu" : "home"}, "", location.href);
  }
  for (const [id, kind, route] of screens) {
    const element = document.getElementById(id);
    element.addEventListener(`shown.bs.${kind}`, () => opening.delete(id));
    element.addEventListener(`show.bs.${kind}`, () => {
      opening.add(id);
      if (id === "serviceModal") serviceFromCart = document.getElementById("cartDrawer").classList.contains("show");
      document.body.classList.add("customer-overlay-open");
      if (!replaying && history.state?.customerScreen !== id) {
        history.pushState({customerScreen: id}, "", `#${route}`);
        window.dispatchEvent(new Event("customer:navigation"));
      }
    });
    element.addEventListener(`hidden.bs.${kind}`, () => {
      // A drawer can close in order to open another dialog. Let that show
      // event run first; dismissing a screen returns to its actual predecessor.
      setTimeout(() => {
        document.body.classList.toggle("customer-overlay-open",
          screens.some(([screen]) => document.getElementById(screen).classList.contains("show")));
        if (!replaying && history.state?.customerScreen === id) history.back();
      }, 0);
    });
  }
  window.addEventListener("popstate", async event => {
    if (replaying) return;
    replaying = true;
    const target = event.state?.customerScreen;
    const closing = [];
    const keepCart = target === "serviceModal" && serviceFromCart;
    for (const [id, kind] of screens) {
      const element = document.getElementById(id);
      if (id !== target && opening.has(id)) {
        await new Promise(resolve => element.addEventListener(`shown.bs.${kind}`, resolve, {once: true}));
      }
      if (element.classList.contains("show") && id !== target && !(keepCart && id === "cartDrawer")) {
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
    document.body.classList.toggle("customer-overlay-open", Boolean(entry));
    replaying = false;
  });

  const drawer = document.getElementById("cartDrawer");
  const service = document.getElementById("serviceModal");
  service.addEventListener("show.bs.modal", () => { guardCartFocus = false; });
  service.addEventListener("shown.bs.modal", () => {
    // The parent drawer had its own focus trap before the modal took over.
    service.focus({preventScroll: true});
  });
  drawer.addEventListener("keydown", event => {
    // During the opening animation focus may still be in the parent drawer.
    if (event.key === "Escape" && service.classList.contains("show")) {
      event.stopImmediatePropagation();
      bootstrap.Modal.getInstance(service)?.hide();
    }
  }, true);
  service.addEventListener("hidden.bs.modal", () => {
    if (!drawer.classList.contains("show")) return;
    // Bootstrap's modal takes over its own focus trap. Restore keyboard access
    // to the still-open cart after the child dialog closes, using public DOM APIs.
    guardCartFocus = true;
    drawer.querySelector(".cart-service").focus({preventScroll: true});
  });
  drawer.addEventListener("hidden.bs.offcanvas", () => { guardCartFocus = false; });
  const cartIsForeground = () => guardCartFocus && drawer.classList.contains("show")
    && !document.querySelector(".modal.show");
  document.addEventListener("focusin", event => {
    if (cartIsForeground() && !drawer.contains(event.target)) drawer.focus({preventScroll: true});
  });
  drawer.addEventListener("keydown", event => {
    if (event.key !== "Tab" || !cartIsForeground()) return;
    const controls = [...drawer.querySelectorAll("a[href],button,input,textarea,select,[tabindex]")]
      .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (!first) { event.preventDefault(); drawer.focus(); return; }
    if (event.shiftKey && (document.activeElement === first || document.activeElement === drawer)) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === drawer)) {
      event.preventDefault(); first.focus();
    }
  });

  return {
    openServiceFromCart() {
      // The cart stays visible and retains its scroll position beneath the popup.
      bootstrap.Modal.getOrCreateInstance(service).show(drawer.querySelector(".cart-service"));
    },
  };
}
