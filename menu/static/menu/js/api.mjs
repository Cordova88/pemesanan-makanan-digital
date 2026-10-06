export function money(value) {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(value);
}

function csrfToken() {
  return (
    document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
    document.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith("csrftoken="))
      ?.split("=")[1] || ""
  );
}

export async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
      ...(options.headers || {}),
    },
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Terjadi kesalahan.");
  }
  return data;
}

export function toast(message) {
  const element = document.createElement("div");
  element.className = "toast align-items-center text-bg-dark border-0 shadow";

  const row = document.createElement("div");
  row.className = "d-flex";
  const content = document.createElement("div");
  content.className = "toast-body";
  content.textContent = message;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "btn-close btn-close-white me-2 m-auto";
  close.setAttribute("data-bs-dismiss", "toast");
  close.setAttribute("aria-label", "Tutup");

  row.append(content, close);
  element.append(row);
  document.querySelector("#toastArea").append(element);
  new bootstrap.Toast(element).show();
}
