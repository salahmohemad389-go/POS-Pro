export const S = {
  user: null,
  settings: {},

  // Caches (Map for O(1) lookup)
  productCache: new Map(),     // product_id -> product
  categoryCache: new Map(),     // category_id -> category
  categoryChildren: new Map(), // parent_id -> [children]
  customerCache: new Map(),    // customer_id -> customer
  supplierCache: new Map(),    // supplier_id -> supplier

  // Pagination state (per page)
  pos: { page: 1, limit: 50, total: 0, q: '', cat: '' },
  productsPage: { page: 1, limit: 50, total: 0, q: '' },
  customersPage: { page: 1, limit: 50, total: 0, q: '' },
  suppliersPage: { page: 1, limit: 50, total: 0, q: '' },
  invoices: { page: 1, limit: 50, total: 0, q: '', filter: 'today', selected: new Set() },
  audit: { page: 1, limit: 100, total: 0, q: '', action: '', date_from: '', date_to: '' },

  // POS cart
  cart: [],
  cartCustomer: null,
  invoiceType: 'sale',

  // Current page in app
  currentPage: 'pos',
};
