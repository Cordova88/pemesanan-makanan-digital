export const state = {
  menu: [],
  cart: { items: [], total: "0.00" },
  chosen: null,
  category: "Semua",
  tableContext: null,
  qrScanner: null,
};

export const TABLE_CONTEXT_KEY = "restaurant_table_context";
export const TABLE_CONTEXT_MAX_AGE = 2 * 60 * 60 * 1000;
