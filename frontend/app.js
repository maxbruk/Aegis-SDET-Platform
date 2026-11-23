/*
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
*/

/**
 * AEGIS STORE — Frontend Single Page Application
 * Engineered for clean UI, immediate hydration, and deterministic Playwright testing.
 */

// Default Configuration
const CONFIG = {
  API_BASE_URL: window.AEGIS_API_URL || 'http://127.0.0.1:3000',
  ALLOW_OFFLINE_MOCK: Boolean(window.AEGIS_ALLOW_OFFLINE_MOCK),
  TAX_RATE: 0.08,
  POLL_INTERVAL_MS: 4000,
};

// Seed Products (High Fidelity Fallback Store)
const DEFAULT_PRODUCTS = [
  {
    id: 1,
    name: "Apex Pro Mechanical Keyboard",
    category: "Electronics",
    price: 149.99,
    stock: 15,
    description: "Aircraft-grade aluminum frame, hot-swappable tactile switches, and PBT double-shot keycaps."
  },
  {
    id: 2,
    name: "Precision Ergonomic Mouse",
    category: "Electronics",
    price: 79.99,
    stock: 24,
    description: "4000 DPI optical sensor, ultra-low latency wireless, and contoured thumb rest."
  },
  {
    id: 3,
    name: "Studio Reference Headphones",
    category: "Audio",
    price: 249.99,
    stock: 8,
    description: "Open-back planar magnetic drivers delivering ultra-wide soundstage and neutral frequency response."
  },
  {
    id: 4,
    name: "USB-C Braided Thunderbolt Cable",
    category: "Accessories",
    price: 29.99,
    stock: 50,
    description: "40Gbps data throughput and 100W Power Delivery with reinforced nylon braiding."
  },
  {
    id: 5,
    name: "Solid Walnut Desk Mat (Extended)",
    category: "Workspace",
    price: 64.99,
    stock: 12,
    description: "Eco-friendly natural wool felt top with non-slip cork base and beveled edge detailing."
  },
  {
    id: 6,
    name: "Ultra-Fast NVMe SSD Enclosure",
    category: "Electronics",
    price: 54.99,
    stock: 18,
    description: "Tool-free aluminum thermal enclosure supporting up to 10Gbps USB 3.2 Gen 2 transfer speeds."
  }
];

// Application State
const state = {
  products: [...DEFAULT_PRODUCTS],
  cart: [],
  user: null,
  activeCategory: 'all',
  searchQuery: '',
  sortOrder: 'featured',
  idempotencyKey: '',
  isOffline: !navigator.onLine,
  isApiReachable: false,
};

// ============================================================================
// Initialization & Instant Hydration
// ============================================================================

function initApp() {
  initState();
  bindEvents();
  renderAll(); // Immediate render without blocking on network!
  checkApiHealth(); // Background probe
  startLiveSync(); // Start real-time live synchronization polling
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

function initState() {
  // Restore User from LocalStorage
  const savedUser = localStorage.getItem('aegis_user');
  if (savedUser) {
    try {
      state.user = JSON.parse(savedUser);
    } catch (e) {
      console.warn('Failed to parse saved user:', e);
    }
  }

  // Restore Cart from LocalStorage
  const savedCart = localStorage.getItem('aegis_cart');
  if (savedCart) {
    try {
      state.cart = JSON.parse(savedCart);
    } catch (e) {
      console.warn('Failed to parse saved cart:', e);
    }
  }

  // Restore Products from LocalStorage if mutated
  const stored = localStorage.getItem('aegis_mock_products');
  if (stored) {
    try {
      state.products = JSON.parse(stored);
    } catch (e) {
      state.products = [...DEFAULT_PRODUCTS];
    }
  } else {
    state.products = [...DEFAULT_PRODUCTS];
    localStorage.setItem('aegis_mock_products', JSON.stringify(state.products));
  }

  // Generate initial Idempotency Key
  generateNewIdempotencyKey();
}

function generateNewIdempotencyKey() {
  state.idempotencyKey = 'idem-' + Math.random().toString(36).substring(2, 10) + '-' + Date.now();
  const elem = document.getElementById('checkout-idempotency-key');
  if (elem) elem.textContent = state.idempotencyKey;
}

// ============================================================================
// Network & API Layer (Real-time Live Sync)
// ============================================================================

let liveSyncTimer = null;

function startLiveSync() {
  if (liveSyncTimer) clearInterval(liveSyncTimer);
  liveSyncTimer = setInterval(async () => {
    if (!state.isOffline) {
      await syncLiveProducts();
    }
  }, CONFIG.POLL_INTERVAL_MS || 2000);
}

async function checkApiHealth() {
  const badge = document.getElementById('api-status-badge');
  const label = document.getElementById('api-status-label');

  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/health`, { method: 'GET', signal: AbortSignal.timeout(1200) });
    if (res.ok) {
      state.isApiReachable = true;
      if (badge) badge.classList.remove('offline');
      if (label) label.textContent = 'API Live';
      await syncLiveProducts();
      return;
    }
  } catch (err) {
    // API offline or unreachable
  }

  state.isApiReachable = false;
  if (badge) badge.classList.add('offline');
  if (label) label.textContent = 'Mock Mode';
}

async function syncLiveProducts() {
  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/v1/products`, { signal: AbortSignal.timeout(1500) });
    if (!res.ok) return;

    const data = await res.json();
    const productList = Array.isArray(data) ? data : (data.data || data.products || []);
    if (!Array.isArray(productList) || productList.length === 0) return;

    let anyChange = false;

    productList.forEach(remoteItem => {
      const localItem = state.products.find(p => p.id === remoteItem.id);
      const newPrice = typeof remoteItem.price === 'number' ? remoteItem.price : parseFloat(remoteItem.price || 0);
      const newStock = typeof remoteItem.stock === 'number' ? remoteItem.stock : parseInt(remoteItem.stock || 0, 10);

      if (localItem) {
        const priceChanged = Math.abs(localItem.price - newPrice) > 0.001;
        const stockChanged = localItem.stock !== newStock;

        if (priceChanged || stockChanged) {
          anyChange = true;
          localItem.price = newPrice;
          localItem.stock = newStock;
          if (remoteItem.name) localItem.name = remoteItem.name;

          // Update corresponding cart item if user has it in cart
          const cartItem = state.cart.find(c => c.productId === localItem.id);
          if (cartItem) {
            cartItem.price = newPrice;
          }

          // In-Place DOM update for ultra-smooth pulse animation
          const cardElem = document.querySelector(`[data-product-id="${localItem.id}"]`);
          if (cardElem) {
            const priceElem = cardElem.querySelector('[data-testid="product-price"]');
            if (priceElem) {
              priceElem.textContent = `$${newPrice.toFixed(2)}`;
              priceElem.classList.remove('price-pulse');
              void priceElem.offsetWidth; // Trigger CSS reflow
              priceElem.classList.add('price-pulse');
            }

            const stockElem = cardElem.querySelector('[data-testid="product-stock"]');
            if (stockElem) {
              if (newStock <= 0) {
                stockElem.className = 'stock-indicator out-of-stock';
                stockElem.textContent = 'Out of Stock';
              } else if (newStock <= 5) {
                stockElem.className = 'stock-indicator low-stock';
                stockElem.textContent = `Only ${newStock} left`;
              } else {
                stockElem.className = 'stock-indicator';
                stockElem.textContent = `${newStock} in stock`;
              }
            }

            const addBtn = cardElem.querySelector('[data-testid="add-to-cart-btn"]');
            if (addBtn) {
              addBtn.disabled = newStock <= 0;
            }
          }

          if (priceChanged) {
            showToast(`📈 Live Price Update: "${localItem.name}" is now $${newPrice.toFixed(2)}`, 'success');
          }
        }
      } else {
        state.products.push({
          id: remoteItem.id,
          name: remoteItem.name,
          category: remoteItem.category ? (remoteItem.category.charAt(0).toUpperCase() + remoteItem.category.slice(1).toLowerCase()) : 'Electronics',
          price: newPrice,
          stock: newStock,
          description: remoteItem.description || 'High-performance precision hardware.'
        });
        anyChange = true;
      }
    });

    if (anyChange) {
      saveCart();
      renderCart();
      renderCheckoutReview();
      renderCatalog();
    }

    if (!state.isApiReachable) {
      state.isApiReachable = true;
      const badge = document.getElementById('api-status-badge');
      const label = document.getElementById('api-status-label');
      if (badge) badge.classList.remove('offline');
      if (label) label.textContent = 'API Live';
    }
  } catch (e) {
    // Background polling network error
  }
}

// ============================================================================
// Event Binding
// ============================================================================

function on(id, event, fn) {
  const el = document.getElementById(id) || document.querySelector(`[data-testid="${id}"]`);
  if (el) el.addEventListener(event, fn);
}

function bindEvents() {
  // Search Input & Clear
  const searchInput = document.getElementById('search-input');
  const searchClear = document.getElementById('search-clear-btn');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value;
      if (searchClear) {
        searchClear.classList.toggle('hidden', state.searchQuery.length === 0);
      }
      renderCatalog();
    });
  }
  if (searchClear) {
    searchClear.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      state.searchQuery = '';
      searchClear.classList.add('hidden');
      renderCatalog();
    });
  }

  // Sort Selection
  on('sort-select', 'change', (e) => {
    state.sortOrder = e.target.value;
    renderCatalog();
  });

  // Category Filter Chips
  const categoryNav = document.getElementById('category-nav');
  if (categoryNav) {
    categoryNav.addEventListener('click', (e) => {
      const chip = e.target.closest('.category-chip');
      if (chip) {
        document.querySelectorAll('.category-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.activeCategory = chip.getAttribute('data-category');
        renderCatalog();
      }
    });
  }

  // Reset Filters Button
  on('reset-filter-btn', 'click', () => {
    if (searchInput) searchInput.value = '';
    state.searchQuery = '';
    state.activeCategory = 'all';
    document.querySelectorAll('.category-chip').forEach(c => {
      c.classList.toggle('active', c.getAttribute('data-category') === 'all');
    });
    if (searchClear) searchClear.classList.add('hidden');
    renderCatalog();
  });

  // Cart Drawer Open / Close
  on('cart-toggle-btn', 'click', openCartDrawer);
  on('cart-close-btn', 'click', closeCartDrawer);
  on('cart-drawer-overlay', 'click', closeCartDrawer);
  on('cart-start-shopping-btn', 'click', closeCartDrawer);
  on('clear-cart-btn', 'click', clearCart);

  // Checkout Modal Open / Close
  on('checkout-btn', 'click', openCheckoutModal);
  on('checkout-close-btn', 'click', closeCheckoutModal);
  on('order-success-continue-btn', 'click', () => {
    closeCheckoutModal();
    closeCartDrawer();
  });

  // Place Order Submission
  on('place-order-btn', 'click', handlePlaceOrder);

  // Auth Modal Open / Close / Tabs
  on('auth-open-btn', 'click', openAuthModal);
  on('auth-close-btn', 'click', closeAuthModal);
  on('tab-login', 'click', () => switchAuthTab('login'));
  on('tab-register', 'click', () => switchAuthTab('register'));

  // Auth Form Submits
  on('login-submit-btn', 'click', handleLogin);
  on('register-submit-btn', 'click', handleRegister);

  // User Menu & Logout
  on('user-menu-btn', 'click', toggleUserDropdown);
  on('logout-btn', 'click', handleLogout);

  // Admin Modal Open / Close / Form
  on('admin-panel-btn', 'click', openAdminModal);
  on('admin-close-btn', 'click', closeAdminModal);
  on('admin-submit-product-btn', 'click', handleAdminCreateProduct);

  // Offline / Online Window Listeners
  window.addEventListener('offline', () => {
    state.isOffline = true;
    updateNetworkStatus();
  });
  window.addEventListener('online', () => {
    state.isOffline = false;
    updateNetworkStatus();
    checkApiHealth();
  });

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    const userMenu = document.getElementById('user-menu');
    const userDropdown = document.getElementById('user-dropdown');
    if (userDropdown && userMenu && !userMenu.contains(e.target)) {
      userDropdown.classList.add('hidden');
    }
  });
}

// ============================================================================
// Render Orchestrator
// ============================================================================

function renderAll() {
  renderCatalog();
  renderCart();
  renderAuthUI();
  updateNetworkStatus();
}

function updateNetworkStatus() {
  const banner = document.getElementById('offline-banner');
  if (banner) {
    banner.classList.toggle('hidden', !state.isOffline);
  }
}

// ============================================================================
// Catalog Rendering
// ============================================================================

function renderCatalog() {
  const grid = document.getElementById('product-grid');
  const emptyState = document.getElementById('catalog-empty');
  const statusText = document.getElementById('catalog-status-text');
  if (!grid) return;

  // Filter by Category
  let filtered = state.products.filter(p => {
    if (state.activeCategory === 'all') return true;
    return (p.category || '').toLowerCase() === state.activeCategory.toLowerCase();
  });

  // Filter by Search
  if (state.searchQuery.trim()) {
    const q = state.searchQuery.toLowerCase();
    filtered = filtered.filter(p => 
      p.name.toLowerCase().includes(q) || 
      (p.description && p.description.toLowerCase().includes(q))
    );
  }

  // Sort
  if (state.sortOrder === 'price-asc') {
    filtered.sort((a, b) => a.price - b.price);
  } else if (state.sortOrder === 'price-desc') {
    filtered.sort((a, b) => b.price - a.price);
  } else if (state.sortOrder === 'name-asc') {
    filtered.sort((a, b) => a.name.localeCompare(b.name));
  }

  // Update Status Text
  if (statusText) {
    statusText.textContent = `Showing ${filtered.length} of ${state.products.length} products`;
  }

  // Handle Empty State
  if (filtered.length === 0) {
    grid.innerHTML = '';
    if (emptyState) emptyState.classList.remove('hidden');
    return;
  }
  if (emptyState) emptyState.classList.add('hidden');

  // Render Cards
  grid.innerHTML = filtered.map(product => {
    const isOutOfStock = product.stock <= 0;
    const isLowStock = product.stock > 0 && product.stock <= 5;
    
    let stockClass = 'stock-indicator';
    let stockLabel = `${product.stock} in stock`;
    if (isOutOfStock) {
      stockClass = 'stock-indicator out-of-stock';
      stockLabel = 'Out of Stock';
    } else if (isLowStock) {
      stockClass = 'stock-indicator low-stock';
      stockLabel = `Only ${product.stock} left`;
    }

    return `
      <article class="product-card" data-testid="product-card" data-product-id="${product.id}">
        <div class="card-media">
          <span class="card-badge" data-testid="product-category">${escapeHtml(product.category)}</span>
          <svg class="card-svg-placeholder" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" aria-hidden="true">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
            <line x1="8" y1="21" x2="16" y2="21"></line>
            <line x1="12" y1="17" x2="12" y2="21"></line>
          </svg>
        </div>
        <div class="card-body">
          <h2 class="product-title" data-testid="product-title">${escapeHtml(product.name)}</h2>
          <p class="product-desc" data-testid="product-description">${escapeHtml(product.description || '')}</p>
          <div class="card-footer">
            <div class="price-group">
              <span class="product-price" data-testid="product-price">$${product.price.toFixed(2)}</span>
              <span class="${stockClass}" data-testid="product-stock">${stockLabel}</span>
            </div>
            <button 
              class="btn btn-primary btn-sm" 
              data-testid="add-to-cart-btn"
              onclick="addToCart(${product.id})"
              ${isOutOfStock ? 'disabled' : ''}
            >
              Add to Cart
            </button>
          </div>
        </div>
      </article>
    `;
  }).join('');
}

// ============================================================================
// Cart Logic & Drawer
// ============================================================================

function openCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const overlay = document.getElementById('cart-drawer-overlay');
  if (drawer) drawer.classList.add('open');
  if (overlay) overlay.classList.remove('hidden');
}

function closeCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const overlay = document.getElementById('cart-drawer-overlay');
  if (drawer) drawer.classList.remove('open');
  if (overlay) overlay.classList.add('hidden');
}

function addToCart(productId, qty = 1) {
  const product = state.products.find(p => p.id === productId);
  if (!product || product.stock <= 0) return;

  const existing = state.cart.find(item => item.productId === productId);
  if (existing) {
    if (existing.quantity + qty <= product.stock) {
      existing.quantity += qty;
    }
  } else {
    state.cart.push({
      productId: product.id,
      name: product.name,
      price: product.price,
      quantity: Math.min(qty, product.stock)
    });
  }

  saveCart();
  renderCart();
  showToast(`Added "${product.name}" to cart`, 'success');

  // If live backend is paired and user authenticated, forward to API
  if (state.user && state.user.token && state.isApiReachable) {
    fetch(`${CONFIG.API_BASE_URL}/api/v1/cart/items`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.user.token}`
      },
      body: JSON.stringify({ product_id: productId, quantity: qty })
    }).catch(() => {});
  }
}

function updateCartItemQty(productId, delta) {
  const itemIndex = state.cart.findIndex(i => i.productId === productId);
  if (itemIndex === -1) return;

  const item = state.cart[itemIndex];
  const product = state.products.find(p => p.id === productId);
  const maxStock = product ? product.stock : 99;

  item.quantity += delta;
  if (item.quantity <= 0) {
    state.cart.splice(itemIndex, 1);
  } else if (item.quantity > maxStock) {
    item.quantity = maxStock;
  }

  saveCart();
  renderCart();

  if (state.user && state.user.token && state.isApiReachable) {
    const newQty = item.quantity <= 0 ? 0 : item.quantity;
    fetch(`${CONFIG.API_BASE_URL}/api/v1/cart/items/${productId}`, {
      method: newQty <= 0 ? 'DELETE' : 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.user.token}`
      },
      ...(newQty > 0 ? { body: JSON.stringify({ quantity: newQty }) } : {})
    }).catch(() => {});
  }
}

function removeCartItem(productId) {
  state.cart = state.cart.filter(i => i.productId !== productId);
  saveCart();
  renderCart();

  if (state.user && state.user.token && state.isApiReachable) {
    fetch(`${CONFIG.API_BASE_URL}/api/v1/cart/items/${productId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${state.user.token}`
      }
    }).catch(() => {});
  }
}

function clearCart() {
  state.cart = [];
  saveCart();
  renderCart();
  showToast('Shopping cart cleared', 'success');

  if (state.user && state.user.token && state.isApiReachable) {
    fetch(`${CONFIG.API_BASE_URL}/api/v1/cart`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${state.user.token}`
      }
    }).catch(() => {});
  }
}

function saveCart() {
  localStorage.setItem('aegis_cart', JSON.stringify(state.cart));
}

function getCartCalculations() {
  const subtotal = state.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  const tax = subtotal * CONFIG.TAX_RATE;
  const total = subtotal + tax;
  const totalItems = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  return { subtotal, tax, total, totalItems };
}

function renderCart() {
  const { subtotal, tax, total, totalItems } = getCartCalculations();

  // Badges
  const badge = document.getElementById('cart-badge-count');
  if (badge) badge.textContent = totalItems.toString();

  const drawerCount = document.getElementById('drawer-item-count');
  if (drawerCount) drawerCount.textContent = `${totalItems} item${totalItems === 1 ? '' : 's'}`;

  // Empty / Filled views
  const emptyView = document.getElementById('cart-empty-view');
  const itemsContainer = document.getElementById('cart-items-container');
  const footer = document.getElementById('cart-footer');
  const itemsList = document.getElementById('cart-items-list');

  if (state.cart.length === 0) {
    if (emptyView) emptyView.classList.remove('hidden');
    if (itemsContainer) itemsContainer.classList.add('hidden');
    if (footer) footer.classList.add('hidden');
  } else {
    if (emptyView) emptyView.classList.add('hidden');
    if (itemsContainer) itemsContainer.classList.remove('hidden');
    if (footer) footer.classList.remove('hidden');

    if (itemsList) {
      itemsList.innerHTML = state.cart.map(item => `
        <div class="cart-item" data-testid="cart-item" data-product-id="${item.productId}">
          <div class="cart-item-info">
            <h3 class="cart-item-name" data-testid="cart-item-title">${escapeHtml(item.name)}</h3>
            <div class="cart-item-price" data-testid="cart-item-price">$${item.price.toFixed(2)} each</div>
          </div>
          <div class="qty-stepper">
            <button class="qty-btn" data-testid="qty-decrement-btn" onclick="updateCartItemQty(${item.productId}, -1)" aria-label="Decrease quantity">−</button>
            <span class="qty-display" data-testid="cart-item-qty">${item.quantity}</span>
            <button class="qty-btn" data-testid="qty-increment-btn" onclick="updateCartItemQty(${item.productId}, 1)" aria-label="Increase quantity">+</button>
          </div>
          <button class="remove-btn" data-testid="cart-item-remove-btn" onclick="removeCartItem(${item.productId})" aria-label="Remove item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" aria-hidden="true">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>
      `).join('');
    }

    // Update Totals
    const subtotalEl = document.getElementById('cart-subtotal');
    const taxEl = document.getElementById('cart-tax');
    const totalEl = document.getElementById('cart-total');
    if (subtotalEl) subtotalEl.textContent = `$${subtotal.toFixed(2)}`;
    if (taxEl) taxEl.textContent = `$${tax.toFixed(2)}`;
    if (totalEl) totalEl.textContent = `$${total.toFixed(2)}`;
  }
}

// ============================================================================
// Checkout Modal & Processing
// ============================================================================

function openCheckoutModal() {
  if (state.cart.length === 0) {
    showToast('Your cart is empty', 'error');
    return;
  }

  generateNewIdempotencyKey();
  const modal = document.getElementById('checkout-modal');
  const formView = document.getElementById('checkout-form-view');
  const successView = document.getElementById('checkout-success-view');
  const errBanner = document.getElementById('checkout-error-banner');

  if (modal) modal.classList.remove('hidden');
  if (formView) formView.classList.remove('hidden');
  if (successView) successView.classList.add('hidden');
  if (errBanner) errBanner.classList.add('hidden');

  // Pre-fill user data if logged in
  if (state.user) {
    const nameInput = document.getElementById('checkout-name');
    const emailInput = document.getElementById('checkout-email');
    if (nameInput && !nameInput.value) nameInput.value = state.user.name || state.user.username || '';
    if (emailInput && !emailInput.value) emailInput.value = state.user.email || '';
  }

  renderCheckoutReview();
}

function closeCheckoutModal() {
  const modal = document.getElementById('checkout-modal');
  if (modal) modal.classList.add('hidden');
}

function renderCheckoutReview() {
  const { subtotal, tax, total } = getCartCalculations();
  const itemsList = document.getElementById('checkout-items-list');
  const subtotalEl = document.getElementById('checkout-subtotal');
  const taxEl = document.getElementById('checkout-tax');
  const totalEl = document.getElementById('checkout-total');
  const payBtnAmount = document.getElementById('checkout-pay-amount');

  if (itemsList) {
    itemsList.innerHTML = state.cart.map(item => `
      <div class="checkout-review-item">
        <span>${escapeHtml(item.name)} × ${item.quantity}</span>
        <span class="font-mono">$${(item.price * item.quantity).toFixed(2)}</span>
      </div>
    `).join('');
  }

  if (subtotalEl) subtotalEl.textContent = `$${subtotal.toFixed(2)}`;
  if (taxEl) taxEl.textContent = `$${tax.toFixed(2)}`;
  if (totalEl) totalEl.textContent = `$${total.toFixed(2)}`;
  if (payBtnAmount) payBtnAmount.textContent = `$${total.toFixed(2)}`;
}

async function handlePlaceOrder() {
  const name = (document.getElementById('checkout-name')?.value || '').trim();
  const email = (document.getElementById('checkout-email')?.value || '').trim();
  const address = (document.getElementById('checkout-address')?.value || '').trim();
  const errBanner = document.getElementById('checkout-error-banner');
  const placeBtn = document.getElementById('place-order-btn');

  if (!name || !email || !address) {
    if (errBanner) {
      errBanner.textContent = 'Please provide your full name, email, and shipping address.';
      errBanner.classList.remove('hidden');
    }
    return;
  }
  if (errBanner) errBanner.classList.add('hidden');

  if (placeBtn) {
    placeBtn.disabled = true;
    placeBtn.innerHTML = 'Processing ACID Settlement...';
  }

  const { total } = getCartCalculations();
  const orderPayload = {
    shipping_address: address,
    customer_name: name,
    customer_email: email,
    items: state.cart.map(i => ({ product_id: i.productId, quantity: i.quantity }))
  };

  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/v1/orders/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': state.idempotencyKey,
        ...(state.user && state.user.token ? { 'Authorization': `Bearer ${state.user.token}` } : {})
      },
      body: JSON.stringify(orderPayload)
    });

    if (res.ok) {
      const data = await res.json();
      const orderRef = data.order_id || (data.id ? `ORD-${data.id}` : `ORD-${Math.floor(100000 + Math.random() * 900000)}`);
      displayOrderSuccess(orderRef, total);
      return;
    } else {
      let errMsg = 'Failed to submit order to API.';
      try {
        const errData = await res.json();
        errMsg = errData.error || errData.message || errMsg;
      } catch (e) {}
      throw new Error(errMsg);
    }
  } catch (err) {
    const isConnRefused = err.name === 'TypeError' || (err.message && err.message.toLowerCase().includes('failed to fetch'));
    if (isConnRefused && CONFIG.ALLOW_OFFLINE_MOCK && !state.isApiReachable) {
      // Explicit offline demo fallback when AEGIS_ALLOW_OFFLINE_MOCK is enabled
      const mockOrderRef = 'ORD-' + Math.floor(100000 + Math.random() * 900000);
      displayOrderSuccess(mockOrderRef, total);
      return;
    }

    if (errBanner) {
      errBanner.textContent = err.message || 'Payment settlement error.';
      errBanner.classList.remove('hidden');
    }
  } finally {
    if (placeBtn) {
      placeBtn.disabled = false;
      placeBtn.innerHTML = `<span>Confirm & Pay</span> <span id="checkout-pay-amount" class="font-mono font-bold">$${total.toFixed(2)}</span>`;
    }
  }
}

function displayOrderSuccess(orderId, totalAmount) {
  const formView = document.getElementById('checkout-form-view');
  const successView = document.getElementById('checkout-success-view');

  const orderIdElem = document.getElementById('confirmed-order-id');
  const totalElem = document.getElementById('confirmed-order-total');
  const idemElem = document.getElementById('confirmed-idempotency-key');

  if (orderIdElem) orderIdElem.textContent = orderId;
  if (totalElem) totalElem.textContent = `$${totalAmount.toFixed(2)}`;
  if (idemElem) idemElem.textContent = state.idempotencyKey;

  if (formView) formView.classList.add('hidden');
  if (successView) successView.classList.remove('hidden');

  // Decrement local stocks
  state.cart.forEach(item => {
    const prod = state.products.find(p => p.id === item.productId);
    if (prod) prod.stock = Math.max(0, prod.stock - item.quantity);
  });
  localStorage.setItem('aegis_mock_products', JSON.stringify(state.products));

  // Clear Cart
  state.cart = [];
  saveCart();
  renderCart();
  renderCatalog();
}

// ============================================================================
// Auth System (Login & Register)
// ============================================================================

function openAuthModal() {
  const modal = document.getElementById('auth-modal');
  if (modal) modal.classList.remove('hidden');
  switchAuthTab('login');
}

function closeAuthModal() {
  const modal = document.getElementById('auth-modal');
  if (modal) modal.classList.add('hidden');
}

function switchAuthTab(tab) {
  const loginBtn = document.getElementById('tab-login');
  const registerBtn = document.getElementById('tab-register');
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const errBanner = document.getElementById('auth-error-banner');

  if (errBanner) errBanner.classList.add('hidden');

  if (tab === 'login') {
    if (loginBtn) loginBtn.classList.add('active');
    if (registerBtn) registerBtn.classList.remove('active');
    if (loginForm) loginForm.classList.remove('hidden');
    if (registerForm) registerForm.classList.add('hidden');
  } else {
    if (loginBtn) loginBtn.classList.remove('active');
    if (registerBtn) registerBtn.classList.add('active');
    if (loginForm) loginForm.classList.add('hidden');
    if (registerForm) registerForm.classList.remove('hidden');
  }
}

async function handleLogin() {
  const email = (document.getElementById('login-email')?.value || '').trim();
  const password = (document.getElementById('login-password')?.value || '').trim();
  const errBanner = document.getElementById('auth-error-banner');

  if (!email || !password) {
    if (errBanner) {
      errBanner.textContent = 'Please enter both email and password.';
      errBanner.classList.remove('hidden');
    }
    return;
  }

  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    if (res.ok) {
      const data = await res.json();
      state.user = {
        id: data.user?.id || 101,
        name: data.user?.username || data.user?.name || email.split('@')[0],
        email: data.user?.email || email,
        role: data.user?.role || (email.includes('admin') ? 'admin' : 'customer'),
        token: data.token || 'jwt-session-token'
      };
      saveUserSession();
      closeAuthModal();
      renderAuthUI();
      showToast(`Welcome back, ${state.user.name}!`, 'success');
      return;
    } else {
      let msg = 'Authentication failed.';
      try {
        const errData = await res.json();
        msg = errData.error || errData.details || msg;
      } catch (e) {}
      throw new Error(msg);
    }
  } catch (err) {
    const isConnRefused = err.name === 'TypeError' || (err.message && err.message.toLowerCase().includes('failed to fetch'));
    if (isConnRefused && CONFIG.ALLOW_OFFLINE_MOCK && !state.isApiReachable) {
      // Explicit offline demo login when AEGIS_ALLOW_OFFLINE_MOCK is enabled
      state.user = {
        id: 101,
        name: email.split('@')[0],
        email: email,
        role: email.includes('admin') ? 'admin' : 'customer',
        token: 'mock-jwt-token-local'
      };
      saveUserSession();
      closeAuthModal();
      renderAuthUI();
      showToast(`Signed in as ${state.user.name}`, 'success');
      return;
    }

    if (errBanner) {
      errBanner.textContent = err.message;
      errBanner.classList.remove('hidden');
    }
  }
}

async function handleRegister() {
  const name = (document.getElementById('register-name')?.value || '').trim();
  const email = (document.getElementById('register-email')?.value || '').trim();
  const password = (document.getElementById('register-password')?.value || '').trim();
  const errBanner = document.getElementById('auth-error-banner');

  if (!name || !email || !password) {
    if (errBanner) {
      errBanner.textContent = 'Please fill out all fields.';
      errBanner.classList.remove('hidden');
    }
    return;
  }
  if (password.length < 8) {
    if (errBanner) {
      errBanner.textContent = 'Password must be at least 8 characters.';
      errBanner.classList.remove('hidden');
    }
    return;
  }

  const username = name.trim().toLowerCase().replace(/[^a-z0-9]/g, '') || ('user' + Date.now());

  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, username, email, password })
    });

    if (res.ok || res.status === 201) {
      const data = await res.json();
      const userObj = data.user || data;
      state.user = {
        id: userObj.id || 102,
        name: userObj.name || userObj.username || name,
        email: userObj.email || email,
        role: userObj.role || 'customer',
        token: data.token || 'jwt-new-user-token'
      };
      saveUserSession();
      closeAuthModal();
      renderAuthUI();
      showToast(`Account created for ${state.user.name}!`, 'success');
      return;
    } else {
      let msg = 'Registration failed.';
      try {
        const errData = await res.json();
        msg = errData.error || errData.details || msg;
      } catch (e) {}
      throw new Error(msg);
    }
  } catch (err) {
    const isConnRefused = err.name === 'TypeError' || (err.message && err.message.toLowerCase().includes('failed to fetch'));
    if (isConnRefused && CONFIG.ALLOW_OFFLINE_MOCK && !state.isApiReachable) {
      // Explicit offline demo registration when AEGIS_ALLOW_OFFLINE_MOCK is enabled
      state.user = {
        id: 102,
        name: name,
        email: email,
        role: 'customer',
        token: 'mock-jwt-token-local'
      };
      saveUserSession();
      closeAuthModal();
      renderAuthUI();
      showToast(`Account created for ${state.user.name}!`, 'success');
      return;
    }

    if (errBanner) {
      errBanner.textContent = err.message;
      errBanner.classList.remove('hidden');
    }
  }
}

function saveUserSession() {
  if (state.user) {
    localStorage.setItem('aegis_user', JSON.stringify(state.user));
    document.cookie = `aegis_token=${state.user.token}; path=/; max-age=86400; SameSite=Lax`;
  }
}

function handleLogout() {
  state.user = null;
  localStorage.removeItem('aegis_user');
  document.cookie = 'aegis_token=; path=/; max-age=0; SameSite=Lax';
  renderAuthUI();
  showToast('Signed out successfully', 'success');
}

function toggleUserDropdown() {
  const dropdown = document.getElementById('user-dropdown');
  if (dropdown) dropdown.classList.toggle('hidden');
}

function renderAuthUI() {
  const authOpenBtn = document.getElementById('auth-open-btn');
  const userMenu = document.getElementById('user-menu');
  const userAvatar = document.getElementById('user-avatar-initial');
  const userName = document.getElementById('user-display-name');
  const userRole = document.getElementById('user-role-tag');
  const userEmail = document.getElementById('user-email-display');
  const adminPanelBtn = document.getElementById('admin-panel-btn');

  if (state.user) {
    if (authOpenBtn) authOpenBtn.classList.add('hidden');
    if (userMenu) userMenu.classList.remove('hidden');

    const initial = (state.user.name || state.user.email || 'U').charAt(0).toUpperCase();
    if (userAvatar) userAvatar.textContent = initial;
    if (userName) userName.textContent = state.user.name || state.user.email;
    if (userRole) userRole.textContent = state.user.role || 'customer';
    if (userEmail) userEmail.textContent = state.user.email;

    if (adminPanelBtn) {
      adminPanelBtn.classList.toggle('hidden', state.user.role !== 'admin');
    }
  } else {
    if (authOpenBtn) authOpenBtn.classList.remove('hidden');
    if (userMenu) userMenu.classList.add('hidden');
    if (adminPanelBtn) adminPanelBtn.classList.add('hidden');
  }
}

// ============================================================================
// Admin Inventory Management Modal
// ============================================================================

function openAdminModal() {
  const modal = document.getElementById('admin-modal');
  if (modal) modal.classList.remove('hidden');
  renderAdminInventoryTable();
}

function closeAdminModal() {
  const modal = document.getElementById('admin-modal');
  if (modal) modal.classList.add('hidden');
}

function renderAdminInventoryTable() {
  const tbody = document.getElementById('admin-inventory-tbody');
  if (!tbody) return;

  tbody.innerHTML = state.products.map(p => `
    <tr data-testid="admin-product-row" data-product-id="${p.id}">
      <td class="font-mono text-xs">${p.id}</td>
      <td class="font-semibold">${escapeHtml(p.name)}</td>
      <td><span class="badge">${escapeHtml(p.category)}</span></td>
      <td class="font-mono">$${p.price.toFixed(2)}</td>
      <td class="font-mono">${p.stock}</td>
      <td>
        <button class="btn btn-ghost btn-sm text-danger" data-testid="admin-delete-product-btn" onclick="handleAdminDeleteProduct(${p.id})">Delete</button>
      </td>
    </tr>
  `).join('');
}

async function handleAdminCreateProduct() {
  const name = (document.getElementById('admin-product-name')?.value || '').trim();
  const price = parseFloat(document.getElementById('admin-product-price')?.value || 0);
  const stock = parseInt(document.getElementById('admin-product-stock')?.value || 0, 10);
  const category = document.getElementById('admin-product-category')?.value || 'Electronics';
  const desc = (document.getElementById('admin-product-desc')?.value || '').trim();

  if (!name || isNaN(price) || price <= 0) {
    showToast('Please enter a valid title and price', 'error');
    return;
  }

  const payload = {
    name,
    category,
    price,
    stock: isNaN(stock) ? 0 : stock,
    description: desc || 'Admin-provisioned catalog product.'
  };

  let createdProduct = null;
  if (!state.user || !state.user.token) {
    if (!CONFIG.ALLOW_OFFLINE_MOCK) {
      showToast('Admin authentication required to create products.', 'error');
      return;
    }
  } else {
    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/api/v1/products`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${state.user.token}`
        },
        body: JSON.stringify(payload)
      });
      if (res.ok || res.status === 201) {
        createdProduct = await res.json();
      } else {
        let errMsg = 'Failed to create product.';
        try {
          const errData = await res.json();
          errMsg = errData.error || errMsg;
        } catch (e) {}
        showToast(errMsg, 'error');
        return;
      }
    } catch (err) {
      const isConnRefused = err.name === 'TypeError' || (err.message && err.message.toLowerCase().includes('failed to fetch'));
      if (!isConnRefused || !CONFIG.ALLOW_OFFLINE_MOCK) {
        showToast(err.message || 'Failed to create product.', 'error');
        return;
      }
    }
  }

  const newId = createdProduct?.id || (Math.max(...state.products.map(p => p.id), 0) + 1);
  const newProd = createdProduct ? {
    id: newId,
    name: createdProduct.name || payload.name,
    category: createdProduct.category || payload.category,
    price: typeof createdProduct.price === 'number' ? createdProduct.price : payload.price,
    stock: typeof createdProduct.stock === 'number' ? createdProduct.stock : payload.stock,
    description: createdProduct.description || payload.description
  } : { id: newId, ...payload };

  state.products.push(newProd);
  localStorage.setItem('aegis_mock_products', JSON.stringify(state.products));

  renderCatalog();
  renderAdminInventoryTable();
  showToast(`Product "${newProd.name}" added to inventory`, 'success');

  // Reset form
  const form = document.getElementById('admin-create-form');
  if (form) form.reset();
}

async function handleAdminDeleteProduct(productId) {
  if (!state.user || !state.user.token) {
    if (!CONFIG.ALLOW_OFFLINE_MOCK) {
      showToast('Admin authentication required to delete products.', 'error');
      return;
    }
  } else {
    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/api/v1/products/${productId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${state.user.token}`
        }
      });
      if (!res.ok && res.status !== 404) {
        showToast('Failed to delete product from API', 'error');
        return;
      }
    } catch (err) {
      const isConnRefused = err.name === 'TypeError' || (err.message && err.message.toLowerCase().includes('failed to fetch'));
      if (!isConnRefused || !CONFIG.ALLOW_OFFLINE_MOCK) {
        showToast(err.message || 'Failed to delete product.', 'error');
        return;
      }
    }
  }

  state.products = state.products.filter(p => p.id !== productId);
  localStorage.setItem('aegis_mock_products', JSON.stringify(state.products));

  renderCatalog();
  renderAdminInventoryTable();
  showToast('Product deleted from inventory', 'success');
}

// ============================================================================
// Utilities
// ============================================================================

function showToast(msg, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('data-testid', 'toast');
  toast.setAttribute('role', 'status');
  toast.innerHTML = `
    <span>${escapeHtml(msg)}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, 3200);
}

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/[&<>"']/g, match => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[match]));
}

// Expose globals for inline HTML event handlers
window.addToCart = addToCart;
window.updateCartItemQty = updateCartItemQty;
window.removeCartItem = removeCartItem;
window.handleAdminDeleteProduct = handleAdminDeleteProduct;
