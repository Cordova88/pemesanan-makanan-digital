import { api, toast } from "./api.mjs";
import { state, TABLE_CONTEXT_KEY, TABLE_CONTEXT_MAX_AGE } from "./state.mjs";

function storedTableContext() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(TABLE_CONTEXT_KEY));
    if (!saved || Date.now() - saved.savedAt > TABLE_CONTEXT_MAX_AGE) {
      sessionStorage.removeItem(TABLE_CONTEXT_KEY);
      return null;
    }
    return saved;
  } catch {
    return null;
  }
}

export async function establishTableContext() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("table");
  if (!token) {
    state.tableContext = storedTableContext();
    return;
  }

  try {
    const table = await api(`/api/orders/tables/${encodeURIComponent(token)}/`);
    state.tableContext = { ...table, savedAt: Date.now() };
    sessionStorage.setItem(
      TABLE_CONTEXT_KEY,
      JSON.stringify(state.tableContext),
    );
    params.delete("table");
    const query = params.toString();
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}${query ? `?${query}` : ""}`,
    );
  } catch {
    console.warn("Invalid table QR token from URL");
  }
}

export function renderOrderType() {
  const orderType = document.querySelector("#orderType").value;
  const scanContainer = document.querySelector("#tableScanContainer");
  const detectedBanner = document.querySelector("#tableDetectedBanner");
  const scannerBox = document.querySelector("#scannerBox");
  const submitButton = document.querySelector("#btnSubmitCheckout");

  if (orderType === "TAKEAWAY") {
    scanContainer.classList.add("d-none");
    stopTableScanner();
    submitButton.disabled = false;
    return;
  }

  scanContainer.classList.remove("d-none");
  if (state.tableContext) {
    detectedBanner.classList.remove("d-none");
    scannerBox.classList.add("d-none");
    document.querySelector("#detectedTableName").textContent =
      state.tableContext.number
        ? `Meja ${state.tableContext.number}`
        : "Meja Terdeteksi";
    submitButton.disabled = false;
  } else {
    detectedBanner.classList.add("d-none");
    scannerBox.classList.remove("d-none");
    submitButton.disabled = true;
  }
}

function tokenFromQr(decodedText) {
  try {
    const url = new URL(decodedText);
    return url.searchParams.get("table") || decodedText.trim();
  } catch {
    return decodedText.trim();
  }
}

export async function stopTableScanner() {
  if (state.qrScanner && state.qrScanner.isScanning) {
    try {
      await state.qrScanner.stop();
      state.qrScanner.clear();
    } catch (error) {
      console.error("Error stopping scanner", error);
    }
  }
  document.querySelector("#cameraViewport").classList.add("d-none");
  document.querySelector("#scannerInitialState").classList.remove("d-none");
  document.querySelector("#scannerBox").classList.remove("scanning");
}

async function startTableScanner() {
  if (!window.Html5Qrcode) {
    toast("Modul pemindai kamera tidak tersedia.");
    return;
  }

  document.querySelector("#scannerInitialState").classList.add("d-none");
  document.querySelector("#cameraViewport").classList.remove("d-none");
  document.querySelector("#scannerBox").classList.add("scanning");
  document.querySelector("#scanStatus").textContent = "Membuka kamera...";
  state.qrScanner = new Html5Qrcode("tableQrReader");

  try {
    await state.qrScanner.start(
      { facingMode: "environment" },
      { fps: 10, qrbox: { width: 160, height: 160 } },
      async (decodedText) => {
        document.querySelector("#scanStatus").textContent =
          "Memvalidasi meja...";
        try {
          const token = tokenFromQr(decodedText);
          const table = await api(
            `/api/orders/tables/${encodeURIComponent(token)}/`,
          );
          state.tableContext = { ...table, savedAt: Date.now() };
          sessionStorage.setItem(
            TABLE_CONTEXT_KEY,
            JSON.stringify(state.tableContext),
          );
          await stopTableScanner();
          renderOrderType();
          toast(`Berhasil: Meja ${table.number}`);
        } catch {
          document.querySelector("#scanStatus").textContent =
            "QR Meja tidak valid!";
          setTimeout(() => {
            if (state.qrScanner && state.qrScanner.isScanning) {
              document.querySelector("#scanStatus").textContent =
                "Arahkan ke QR Meja...";
            }
          }, 2000);
        }
      },
      () => {},
    );
    document.querySelector("#scanStatus").textContent =
      "Arahkan ke QR Meja...";
  } catch {
    toast("Gagal mengakses kamera. Pastikan izin kamera diberikan.");
    await stopTableScanner();
  }
}

export function bindTableScanner() {
  document.querySelector("#orderType").addEventListener("change", renderOrderType);
  document
    .querySelector("#btnStartScan")
    .addEventListener("click", startTableScanner);
  document
    .querySelector("#btnStopScan")
    .addEventListener("click", stopTableScanner);
  document.querySelector("#btnRescan").addEventListener("click", () => {
    state.tableContext = null;
    sessionStorage.removeItem(TABLE_CONTEXT_KEY);
    renderOrderType();
  });
  document
    .querySelector("#checkoutModal")
    .addEventListener("hidden.bs.modal", stopTableScanner);
}
