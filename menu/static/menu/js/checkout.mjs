import { api, money, toast } from "./api.mjs?v=customer-p4-r5";
import { state } from "./state.mjs?v=customer-p4-r5";
import { createFoodVisual } from './menu-card.mjs?v=customer-p4-r5';
import { renderOrderType } from "./table-scanner.mjs?v=customer-p4-r5";
import { flushCartNotes } from "./cart.mjs?v=customer-p4-r5";

let reviewing = false;
let submitting = false;
let reviewedData = null;

function showDetails() {
  reviewing = false;
  reviewedData = null;
  document.querySelector("#checkoutDetails").hidden = false;
  document.querySelector("#checkoutReview").hidden = true;
  document.querySelector("#checkoutTitle").textContent = "Detail pemesanan";
  document.querySelector("#btnSubmitCheckout").textContent = "Lanjut konfirmasi";
  document.querySelector("#checkoutHint").textContent = "Periksa detail sebelum melanjutkan.";
  renderOrderType();
}

function showReview(formData) {
  // Submit exactly the details displayed in this read-only review.
  reviewedData = Object.freeze({
    ...formData,
    table_token: formData.order_type === "DINE_IN" ? state.tableContext?.token : null,
  });
  const dineIn = formData.order_type === "DINE_IN";
  document.body.classList.toggle("dine-in", dineIn);
  document.querySelector("#reviewServiceLabel").textContent = dineIn ? "Makan di tempat" : "Bawa pulang";
  document.querySelector("#reviewServiceDetail").textContent = dineIn ? `Meja ${state.tableContext.number} · RasaKita` : "RasaKita · Pesanan untuk dibawa";
  const items = document.querySelector("#reviewItems");
  items.replaceChildren();
  state.cart.items.forEach(item => {
    const card = document.createElement("div");
    card.className = "paper-card mb-3";
    const title = document.createElement("strong");
    title.textContent = item.name;
    const price = document.createElement("strong");
    price.className = "accent";
    price.textContent = money(item.line_total);
    const menu = state.menu.find(menu=>menu.id===item.menu_item_id) || {};
    const image = createFoodVisual(item, { eager: true });
    image.classList.add("review-image");
    const info=document.createElement("div"); info.className="review-item-heading"; info.append(title,price);
    card.classList.add("review-item");
    card.append(image,info);
    const detail=document.createElement("div"); detail.className="review-detail";
    const heading=document.createElement("h4"); heading.textContent="Detail Pesanan"; detail.append(heading);
    const addRow=(kind,label,value)=>{
      const row=document.createElement("p"); row.className=`detail-row detail-${kind}`;
      const caption=document.createElement("span");caption.textContent=label;
      const text=document.createElement("strong");text.textContent=value;
      row.append(caption,text);detail.append(row);
    };
    if(item.variants.length) addRow("spice","Tingkat Pedas",item.variants.map(option=>option.name).join(" · "));
    addRow("addon","Tambahan",item.addons.length ? item.addons.map(option=>{
      const extra=(menu.addons||[]).find(addon=>addon.id===option.id);
      return option.name+(Number(extra?.price) > 0 ? ` +${money(extra.price).replace(/^Rp/, "")}` : "");
    }).join(", ") : "Tanpa tambahan");
    addRow("note",item.note || "Tanpa catatan","");
    addRow("portion","Porsi",`${item.quantity} Porsi`);
    card.append(detail);
    items.append(card);
  });
  if (formData.note) {
    const note = document.createElement("p");
    note.className = "small muted";
    note.textContent = `Catatan: ${formData.note}`;
    items.append(note);
  }
  document.querySelector("#reviewSubtotal").textContent = money(state.cart.total);
  document.querySelector("#reviewTotal").textContent = money(state.cart.total);
  reviewing = true;
  document.querySelector("#checkoutDetails").hidden = true;
  document.querySelector("#checkoutReview").hidden = false;
  document.querySelector("#checkoutTitle").textContent = "Konfirmasi pesanan";
  document.querySelector("#btnSubmitCheckout").textContent = "Buat pesanan";
  document.querySelector("#checkoutHint").textContent = "Tidak perlu membuat akun.";
  document.querySelector("#checkoutModal").scrollTop = 0;
}

async function openCheckout() {
  if (!await flushCartNotes()) return;
  const cartDrawer = document.querySelector("#cartDrawer");
  const drawer = bootstrap.Offcanvas.getInstance(cartDrawer);
  const form = document.querySelector("#checkoutForm");
  if (!form.elements.customer_name.value) form.elements.customer_name.value = "Pelanggan";
  const formData=Object.fromEntries(new FormData(form));
  if (formData.order_type === "DINE_IN" && !state.tableContext) showDetails();
  else showReview(formData);
  const show = () => bootstrap.Modal.getOrCreateInstance(document.querySelector("#checkoutModal")).show();
  if (drawer && cartDrawer.classList.contains("show")) {
    cartDrawer.addEventListener("hidden.bs.offcanvas", show, { once: true });
    drawer.hide();
  } else {
    show();
  }
}

async function submitCheckout(event) {
  event.preventDefault();
  if (submitting) return;
  const formData = reviewing
    ? reviewedData
    : Object.fromEntries(new FormData(event.target));
  const errorMessage = document.querySelector("#checkoutError");
  errorMessage.classList.add("d-none");

  if (formData.order_type === "DINE_IN" && !state.tableContext) {
    errorMessage.textContent = "Mohon pindai QR meja terlebih dahulu.";
    errorMessage.classList.remove("d-none");
    return;
  }

  if (!reviewing) {
    showReview(formData);
    return;
  }

  const payload = reviewedData;

  try {
    submitting = true;
    document.querySelector("#btnSubmitCheckout").disabled = true;
    const result = await api("/api/orders/checkout/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    bootstrap.Modal.getInstance(
      document.querySelector("#checkoutModal"),
    ).hide();
    toast("Pesanan berhasil dibuat!");
    const payChoice = document.querySelector('input[name="payment_choice"]:checked')?.value || "CASHIER";
    const payMode = payChoice === "ONLINE" ? "online" : "cashier";
    window.location.href = `/orders/${result.public_id}/?pay_mode=${payMode}`;
  } catch (error) {
    errorMessage.textContent = error.message;
    errorMessage.classList.remove("d-none");
  } finally {
    submitting = false;
    document.querySelector("#btnSubmitCheckout").disabled = false;
  }
}

function updatePaymentMethodUI() {
  const isOnline = document.querySelector('input[name="payment_choice"]:checked')?.value === "ONLINE";
  const title = document.querySelector("#selectedPaymentTitle");
  const desc = document.querySelector("#selectedPaymentDesc");
  const exp = document.querySelector("#selectedPaymentExp");
  const icon = document.querySelector("#selectedPaymentIcon");
  const noticeTitle = document.querySelector("#reviewNoticeTitle");
  const noticeDesc = document.querySelector("#reviewNoticeDesc");
  const submitBtn = document.querySelector("#btnSubmitCheckout");

  if (isOnline) {
    if (title) title.textContent = "Bayar Online (QRIS)";
    if (desc) desc.textContent = "Scan kode QR untuk bayar otomatis.";
    if (exp) exp.innerHTML = "Kode QR pembayaran otomatis akan muncul setelah pesanan dibuat. <span class='text-danger fw-semibold'>Ubah ›</span>";
    if (noticeTitle) noticeTitle.textContent = "Bayar Online Otomatis";
    if (noticeDesc) noticeDesc.textContent = "Scan kode QR setelah pesanan dibuat untuk menyelesaikan transaksi.";
    if (reviewing && submitBtn) submitBtn.textContent = "Buat pesanan & Bayar QR";
    if (icon) {
      icon.className = "";
      icon.style.cssText = "width:44px;height:44px;flex:0 0 44px;border-radius:12px;background:#fee2e2;color:#b91c1c;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;border:1px solid #fca5a5;";
      icon.textContent = "QRIS";
    }
  } else {
    if (title) title.textContent = "Bayar di kasir";
    if (desc) desc.textContent = "Tunjukkan kode pesanan ke kasir.";
    if (exp) exp.innerHTML = "Pesanan dibuat setelah kamu menekan tombol. <span class='text-danger fw-semibold'>Pilih cara bayar ›</span>";
    if (noticeTitle) noticeTitle.textContent = "Belum dibayar";
    if (noticeDesc) noticeDesc.textContent = "Lanjutkan pembayaran langsung ke kasir.";
    if (reviewing && submitBtn) submitBtn.textContent = "Buat pesanan";
    if (icon) {
      icon.className = "payment-bag";
      icon.style.cssText = "";
      icon.textContent = "";
    }
  }
}

export function bindCheckout() {
  document
    .querySelector("#checkoutButton")
    .addEventListener("click", openCheckout);
  document
    .querySelector("#checkoutForm")
    .addEventListener("submit", submitCheckout);

  const trigger = document.querySelector("#paymentMethodTrigger");
  const optionsContainer = document.querySelector("#paymentOptionsContainer");
  const chevron = document.querySelector("#paymentMethodChevron");
  if (trigger && optionsContainer) {
    trigger.addEventListener("click", () => {
      const isHidden = optionsContainer.classList.toggle("d-none");
      if (chevron) {
        chevron.style.transform = isHidden ? "rotate(0deg)" : "rotate(90deg)";
      }
    });
  }

  document.querySelectorAll('input[name="payment_choice"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      updatePaymentMethodUI();
      if (optionsContainer) {
        optionsContainer.classList.add("d-none");
        if (chevron) chevron.style.transform = "rotate(0deg)";
      }
    });
  });
}

