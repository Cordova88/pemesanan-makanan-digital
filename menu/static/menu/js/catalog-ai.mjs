// This invitation is local UI text; it does not call an AI provider.
export function bindCatalogAi() {
  const helper = document.querySelector("#catalogAi");
  const menu = document.querySelector("#menuView");
  if (!helper || !menu) return;

  const text = helper.querySelector(".catalog-ai-text");
  const message = "Ada yang bisa aku bantu?";
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let timer;
  let active = false;

  const schedule = (callback, delay) => {
    clearTimeout(timer);
    timer = setTimeout(callback, delay);
  };
  const pinned = () => helper.matches(":hover, :focus-within");

  function hide() {
    helper.classList.remove("is-speaking", "is-typing");
    schedule(start, 8000);
  }

  function start() {
    if (!active) return;
    if (pinned() || motion.matches) {
      reveal();
      return;
    }
    text.textContent = "";
    helper.classList.add("is-speaking", "is-typing");
    let index = 0;
    function typeNext() {
      text.textContent = message.slice(0, ++index);
      if (index < message.length) schedule(typeNext, 65);
      else {
        helper.classList.remove("is-typing");
        schedule(hide, 4000);
      }
    }
    schedule(typeNext, 240);
  }

  function reveal() {
    if (!active) return;
    clearTimeout(timer);
    text.textContent = message;
    helper.classList.add("is-speaking");
    helper.classList.remove("is-typing");
  }

  function update(force = false) {
    const visible = !document.hidden && !menu.classList.contains("d-none")
      && !document.body.classList.contains("customer-overlay-open");
    if (!force && visible === active) return;
    active = visible;
    clearTimeout(timer);
    helper.classList.remove("is-speaking", "is-typing");
    if (active) {
      if (motion.matches || pinned()) reveal();
      else schedule(start, 900);
    }
  }

  helper.addEventListener("pointerenter", reveal);
  helper.addEventListener("focusin", reveal);
  const resume = () => {
    if (active && !pinned() && !motion.matches) schedule(hide, 4000);
  };
  helper.addEventListener("pointerleave", resume);
  helper.addEventListener("focusout", resume);
  const observer = new MutationObserver(() => update());
  observer.observe(menu, { attributes: true, attributeFilter: ["class"] });
  observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });
  document.addEventListener("visibilitychange", () => update());
  motion.addEventListener("change", () => update(true));
  window.addEventListener("pagehide", () => {
    active = false;
    clearTimeout(timer);
  });
  window.addEventListener("pageshow", () => update());
  update();
}
