/*
 * Archivo: app.js
 * Descripcion: Archivo principal del frontend encargado de productos, autenticacion, carrito, pedidos, checkout, feedback visual y eventos de interfaz.
 * Dependencias: Django templates, endpoints REST del backend, localStorage, DOM API, Fetch API, style.css
 */

console.log("APP CARGADO");

// =============================================================================
//  ENDPOINTS DE LA API
// =============================================================================

const api = {
    products: "/api/products/",
    authRegister: "/api/auth/register/",
    authLogin: "/api/auth/login/",
    authLogout: "/api/auth/logout/",
    me: "/api/auth/me/",
    cartGet: "/api/cart/",
    cartAdd: "/api/cart/add/",
    cartDecrease: "/api/cart/decrease/",
    cartRemove: "/api/cart/remove/",
    checkout: "/api/orders/checkout/",
    myOrders: "/api/orders/my/",

    cancelOrder: (orderId) => `/api/orders/cancel/${orderId}/`,
};

// =============================================================================
//  UTILIDADES GENERALES
// =============================================================================

/*
 * Nombre: escapeHtml
 * Descripcion: Escapa caracteres especiales para evitar insercion insegura de HTML dentro del DOM.
 */
function escapeHtml(str) {
    if (!str) return "";

    const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    };

    return String(str).replace(/[&<>"']/g, (char) => map[char]);
}

function getCookie(name) {
    if (!document.cookie || document.cookie === "") return null;

    const cookies = document.cookie.split(";");

    for (let cookie of cookies) {
        cookie = cookie.trim();

        if (cookie.startsWith(name + "=")) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }

    return null;
}

/*
 * Nombre: csrfHeaders
 * Descripcion: Construye los encabezados necesarios para enviar JSON y token CSRF al backend Django.
 */
function csrfHeaders() {
    return {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
    };
}

function isEmpty(value) {
    return !value || value.trim() === "";
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function normalizeStatus(status) {
    return (status || "pendiente").toLowerCase().trim();
}

// =============================================================================
//  FEEDBACK VISUAL
// =============================================================================

/*
 * Nombre: showToast
 * Descripcion: Muestra una notificacion temporal para acciones importantes del usuario.
 */
function showToast(message, type = "info", duration = 3000) {
    const container = document.getElementById("toast-container");

    if (!container) return;

    const toast = document.createElement("div");

    toast.classList.add("toast", type);
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, duration);
}

/*
 * Nombre: closeModalSafely
 * Descripcion: Cierra un modal o drawer moviendo primero el foco para evitar advertencias de accesibilidad.
 */
function closeModalSafely(modal, focusTarget = null) {
    if (!modal) return;

    const activeElement = document.activeElement;

    const focusIsInsideModal =
        activeElement instanceof HTMLElement && modal.contains(activeElement);

    if (focusIsInsideModal) {
        if (focusTarget instanceof HTMLElement) {
            focusTarget.focus();
        } else {
            activeElement.blur();
        }
    }

    requestAnimationFrame(() => {
        modal.setAttribute("aria-hidden", "true");
        modal.classList.remove("open");
    });
}

function showAuthFeedback(message, type = "error") {
    const feedback = document.getElementById("auth-feedback");

    if (!feedback) return;

    feedback.textContent = message;
    feedback.className = `auth-feedback ${type}`;
    feedback.style.display = "block";
}

function clearAuthFeedback() {
    const feedback = document.getElementById("auth-feedback");

    if (!feedback) return;

    feedback.textContent = "";
    feedback.className = "auth-feedback";
    feedback.style.display = "none";
}

function showCartFeedback(message, type = "success") {
    const cartFeedback = document.getElementById("cart-feedback");

    if (!cartFeedback) return;

    cartFeedback.textContent = message;
    cartFeedback.className = `cart-feedback ${type}`;
    cartFeedback.style.display = "block";
}

function clearCartFeedback() {
    const cartFeedback = document.getElementById("cart-feedback");

    if (!cartFeedback) return;

    cartFeedback.textContent = "";
    cartFeedback.className = "cart-feedback";
    cartFeedback.style.display = "none";
}

function showOrdersFeedback(message, type = "success") {
    const feedback = document.getElementById("orders-feedback");

    if (!feedback) return;

    feedback.textContent = message;
    feedback.className = `orders-feedback ${type}`;
    feedback.style.display = "block";
}

function clearOrdersFeedback() {
    const feedback = document.getElementById("orders-feedback");

    if (!feedback) return;

    feedback.textContent = "";
    feedback.className = "orders-feedback";
    feedback.style.display = "none";
}

// =============================================================================
//  CONFIRMACION DE CANCELACION DE ORDEN
// =============================================================================

let pendingCancelOrderId = null;
let pendingCancelButton = null;

/*
 * Nombre: showOrderCancelConfirm
 * Descripcion: Muestra la confirmacion visual antes de cancelar una orden.
 */
function showOrderCancelConfirm(orderId, btn) {
    pendingCancelOrderId = orderId;
    pendingCancelButton = btn;

    const box = document.getElementById("orders-confirm");
    const text = document.getElementById("orders-confirm-text");

    if (!box || !text) return;

    clearOrdersFeedback();

    text.textContent = `¿Seguro que quieres cancelar el pedido #${orderId}?`;
    box.style.display = "block";
}

function hideOrderCancelConfirm() {
    pendingCancelOrderId = null;
    pendingCancelButton = null;

    const box = document.getElementById("orders-confirm");

    if (box) {
        box.style.display = "none";
    }
}

// =============================================================================
//  AUTENTICACION
// =============================================================================

/*
 * Nombre: setAuthUI
 * Descripcion: Actualiza los botones y etiquetas segun el estado de sesion del usuario.
 */
function setAuthUI(isLoggedIn, user = null) {
    const btnLogin = document.getElementById("open-auth");
    const btnLogout = document.getElementById("logout-btn");
    const labelUser = document.getElementById("user-label");
    const btnMyOrders = document.getElementById("my-orders-btn");

    if (btnLogin) btnLogin.style.display = isLoggedIn ? "none" : "inline-flex";
    if (btnLogout) btnLogout.style.display = isLoggedIn ? "inline-flex" : "none";
    if (btnMyOrders) btnMyOrders.style.display = isLoggedIn ? "inline-flex" : "none";

    if (labelUser) {
        labelUser.textContent = isLoggedIn
            ? (user?.username || user?.email || "Usuario")
            : "";
    }
}

/*
 * Nombre: refreshAuthState
 * Descripcion: Consulta el backend para verificar si hay una sesion activa.
 */
async function refreshAuthState() {
    try {
        const res = await fetch(api.me, {
            credentials: "include",
        });

        if (!res.ok) throw new Error("Sin sesion activa");

        const user = await res.json();

        setAuthUI(true, user);

        return true;
    } catch {
        setAuthUI(false);

        return false;
    }
}

/*
 * Nombre: registerUser
 * Descripcion: Envia los datos de registro al backend y maneja errores devueltos por la API.
 */
async function registerUser(name, email, password) {
    const res = await fetch(api.authRegister, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify({ username: name, email, password }),
    });

    if (!res.ok) {
        let msg = "No se pudo registrar la cuenta";

        try {
            const data = await res.json();
            msg = data?.error || data?.detail || data?.message || msg;
        } catch {
            // Se conserva el mensaje por defecto.
        }

        throw new Error(msg);
    }

    return await res.json();
}

/*
 * Nombre: loginUser
 * Descripcion: Envia credenciales al backend para iniciar sesion con correo o usuario.
 */
async function loginUser(emailOrUsername, password) {
    const res = await fetch(api.authLogin, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify({
            email: emailOrUsername,
            username: emailOrUsername,
            password,
        }),
    });

    if (!res.ok) {
        let msg = "No se pudo iniciar sesion";

        try {
            const data = await res.json();
            msg = data?.error || data?.detail || data?.message || msg;
        } catch {
            // Se conserva el mensaje por defecto.
        }

        throw new Error(msg);
    }

    return await res.json();
}

/*
 * Nombre: logoutUser
 * Descripcion: Cierra la sesion y limpia estados visuales relacionados.
 */
async function logoutUser() {
    await fetch(api.authLogout, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
    });

    localStorage.removeItem("cart");

    setAuthUI(false);
    clearCartFeedback();
    clearOrdersFeedback();
    hideOrderCancelConfirm();

    await updateCartUI();
    await refreshProductsUI();
}

// =============================================================================
//  PEDIDOS
// =============================================================================

/*
 * Nombre: fetchMyOrders
 * Descripcion: Obtiene los pedidos del usuario autenticado.
 */
async function fetchMyOrders() {
    const res = await fetch(api.myOrders, {
        credentials: "include",
    });

    if (res.status === 401 || res.status === 403) {
        return { notLogged: true, orders: [] };
    }

    if (!res.ok) {
        throw new Error("No se pudieron cargar los pedidos");
    }

    return await res.json();
}

/*
 * Nombre: cancelOrder
 * Descripcion: Solicita al backend cancelar una orden especifica.
 */
async function cancelOrder(orderId) {
    const res = await fetch(api.cancelOrder(orderId), {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
    });

    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudo cancelar la orden");
    }

    return data;
}

/*
 * Nombre: renderMyOrders
 * Descripcion: Renderiza el historial de pedidos, estados, productos, totales y acciones disponibles.
 */
function renderMyOrders(data) {
    const body = document.getElementById("orders-body");

    if (!body) return;

    if (data?.notLogged) {
        body.innerHTML = `<p class="muted">Debes iniciar sesion para ver tus pedidos.</p>`;
        return;
    }

    const orders = data?.orders || [];

    if (!orders.length) {
        body.innerHTML = `
            <div class="empty-orders">
                <div class="empty-orders-icon">Historial</div>

                <h3>Aún no tienes pedidos</h3>

                <p>
                    Cuando realices una compra, aparecerá aquí tu historial.
                </p>

                <button class="btn empty-orders-btn">
                    Explorar productos
                </button>
            </div>
        `;

        document
            .querySelector(".empty-orders-btn")
            ?.addEventListener("click", () => {
                const ordersModal = document.getElementById("orders-modal");
                const myOrdersBtn = document.getElementById("my-orders-btn");

                closeModalSafely(ordersModal, myOrdersBtn);

                document
                    .getElementById("productos")
                    ?.scrollIntoView({
                        behavior: "smooth",
                    });
            });

        return;
    }

    body.innerHTML = orders
        .map((order) => {
            const statusNorm = normalizeStatus(order.status);

            const itemsHtml = (order.items || [])
                .map((item) => `
                    <div class="order-item">
                        <div>
                            <strong>${escapeHtml(item.product?.name || "Producto")}</strong>

                            <div class="muted">
                                $${Number(item.product?.price || 0).toFixed(2)}
                                x ${Number(item.quantity || 0)}
                            </div>
                        </div>

                        <div>
                            <strong>$${Number(item.line_total || 0).toFixed(2)}</strong>
                        </div>
                    </div>
                `)
                .join("");

            const cancelButton = statusNorm !== "cancelado"
                ? `
                    <button class="btn small cancel-order-btn" data-id="${order.id}">
                        Cancelar pedido
                    </button>
                `
                : `<span class="muted">Pedido cancelado</span>`;

            const fechaStr = order.date_ordered
                ? new Date(order.date_ordered).toLocaleString()
                : "";

            return `
                <div class="order-card">
                    <div class="order-head">
                        <div>
                            <strong>Pedido #${order.id}</strong>

                            <span class="order-status status-${escapeHtml(statusNorm)}">
                                ${escapeHtml(order.status || "pendiente")}
                            </span>
                        </div>

                        <div class="muted">${fechaStr}</div>
                    </div>

                    <div class="order-items">
                        ${itemsHtml}
                    </div>

                    <div class="order-total" style="margin-top: 10px;">
                        <span>Total</span>
                        <strong>$${Number(order.total || 0).toFixed(2)}</strong>
                    </div>

                    <div style="margin-top: 12px;">
                        ${cancelButton}
                    </div>
                </div>
            `;
        })
        .join("");

    document.querySelectorAll(".cancel-order-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            showOrderCancelConfirm(btn.dataset.id, btn);
        });
    });
}

// =============================================================================
//  PRODUCTOS
// =============================================================================

let catalogProducts = [];

/*
 * Nombre: fetchProducts
 * Descripcion: Obtiene el listado de productos desde el backend.
 */
async function fetchProducts() {
    try {
        const res = await fetch(api.products);

        if (!res.ok) throw new Error("No se pudieron cargar los productos");

        return await res.json();
    } catch (err) {
        console.error("fetchProducts:", err);

        return [];
    }
}

function renderProductsSkeleton(count = 6) {
    const container = document.getElementById("product-list");
    const resultsInfo = document.getElementById("catalog-results-info");

    if (resultsInfo) {
        resultsInfo.textContent = "Cargando productos...";
    }

    if (!container) return;

    container.innerHTML = Array(count)
        .fill(0)
        .map(() => `
            <div class="skeleton-card">
                <div class="skeleton-image"></div>
                <div class="skeleton-line medium"></div>
                <div class="skeleton-line"></div>
                <div class="skeleton-line short"></div>
            </div>
        `)
        .join("");
}

/*
 * Nombre: renderProducts
 * Descripcion: Renderiza productos, estados de stock y botones para agregar al carrito.
 */
function renderProducts(products, options = {}) {
    const container = document.getElementById("product-list");
    const isFiltered = options.isFiltered || false;

    if (!container) return;

    if (!products.length) {
        const emptyTitle = isFiltered
            ? "No se encontraron productos"
            : "No hay productos disponibles";

        const emptyText = isFiltered
            ? "Ajusta la busqueda o cambia los filtros para ver mas resultados."
            : "Intenta nuevamente mas tarde.";

        const emptyAction = isFiltered
            ? `
                <button class="btn clear-catalog-filters">
                    Limpiar filtros
                </button>
            `
            : `
                <button class="btn retry-products-btn">
                    Recargar productos
                </button>
            `;

        container.innerHTML = `
            <div class="empty-products">
                <div class="empty-products-icon">Sin resultados</div>

                <h3>${emptyTitle}</h3>

                <p>
                    ${emptyText}
                </p>

                ${emptyAction}
            </div>
        `;

        document
            .querySelector(".retry-products-btn")
            ?.addEventListener("click", async () => {
                renderProductsSkeleton();

                catalogProducts = await fetchProducts();

                applyCatalogFilters();
            });

        document
            .querySelector(".clear-catalog-filters")
            ?.addEventListener("click", () => {
                resetCatalogControls();
                applyCatalogFilters();
            });

        return;
    }

    container.innerHTML = products
        .map((product) => {
            const stock = Number(product.stock || 0);

            let stockLabel = "";

            if (stock === 0) {
                stockLabel = `<p class="stock-label stock-empty">Sin stock</p>`;
            } else if (stock <= 3) {
                stockLabel = `<p class="stock-label stock-low">Ultimas unidades (${stock})</p>`;
            } else {
                stockLabel = `<p class="muted stock-label">Stock disponible: ${stock}</p>`;
            }

            const addButton = stock > 0
                ? `<button class="btn add-to-cart" data-id="${product.id}">Agregar</button>`
                : `<button class="btn add-to-cart" disabled>Sin stock</button>`;

            return `
                <article class="product-card" data-id="${product.id}">
                    <img
                        src="${escapeHtml(product.image) || "/static/store/img/placeholder.png"}"
                        alt="${escapeHtml(product.name)}"
                    />

                    <div class="product-info">
                        <h3>${escapeHtml(product.name)}</h3>

                        <p class="muted">${escapeHtml(product.description || "")}</p>

                        ${stockLabel}

                        <div class="price">
                            <p>$${Number(product.price).toFixed(2)}</p>

                            ${addButton}
                        </div>
                    </div>
                </article>
            `;
        })
        .join("");

    document.querySelectorAll(".add-to-cart").forEach((btn) => {
        btn.addEventListener("click", () => {
            addToCart(Number(btn.dataset.id), 1);
        });
    });
}

/*
 * Nombre: getFilteredCatalogProducts
 * Descripcion: Aplica busqueda, disponibilidad y ordenamiento sobre el catalogo cargado.
 */
function getFilteredCatalogProducts() {
    const searchInput = document.getElementById("product-search");
    const stockFilter = document.getElementById("product-stock-filter");
    const sortSelect = document.getElementById("product-sort");

    const searchValue = (searchInput?.value || "").toLowerCase().trim();
    const stockValue = stockFilter?.value || "all";
    const sortValue = sortSelect?.value || "default";

    let products = [...catalogProducts];

    if (searchValue) {
        products = products.filter((product) => {
            const name = String(product.name || "").toLowerCase();
            const description = String(product.description || "").toLowerCase();

            return name.includes(searchValue) || description.includes(searchValue);
        });
    }

    if (stockValue === "available") {
        products = products.filter((product) => Number(product.stock || 0) > 0);
    }

    if (stockValue === "low") {
        products = products.filter((product) => {
            const stock = Number(product.stock || 0);

            return stock > 0 && stock <= 3;
        });
    }

    if (stockValue === "empty") {
        products = products.filter((product) => Number(product.stock || 0) === 0);
    }

    if (sortValue === "price-asc") {
        products.sort((a, b) => Number(a.price || 0) - Number(b.price || 0));
    }

    if (sortValue === "price-desc") {
        products.sort((a, b) => Number(b.price || 0) - Number(a.price || 0));
    }

    if (sortValue === "stock-desc") {
        products.sort((a, b) => Number(b.stock || 0) - Number(a.stock || 0));
    }

    if (sortValue === "name-asc") {
        products.sort((a, b) =>
            String(a.name || "").localeCompare(String(b.name || ""))
        );
    }

    return products;
}

function updateCatalogResultsInfo(filteredCount, totalCount) {
    const resultsInfo = document.getElementById("catalog-results-info");

    if (!resultsInfo) return;

    if (!totalCount) {
        resultsInfo.textContent = "No hay productos cargados.";
        return;
    }

    if (filteredCount === totalCount) {
        resultsInfo.textContent = `Mostrando ${totalCount} producto(s).`;
        return;
    }

    resultsInfo.textContent = `Mostrando ${filteredCount} de ${totalCount} producto(s).`;
}

function resetCatalogControls() {
    const searchInput = document.getElementById("product-search");
    const stockFilter = document.getElementById("product-stock-filter");
    const sortSelect = document.getElementById("product-sort");

    if (searchInput) searchInput.value = "";
    if (stockFilter) stockFilter.value = "all";
    if (sortSelect) sortSelect.value = "default";
}

function applyCatalogFilters() {
    const filteredProducts = getFilteredCatalogProducts();

    updateCatalogResultsInfo(filteredProducts.length, catalogProducts.length);

    renderProducts(filteredProducts, {
        isFiltered: filteredProducts.length !== catalogProducts.length,
    });
}

/*
 * Nombre: initCatalogControls
 * Descripcion: Conecta los controles del catalogo con el filtrado dinamico de productos.
 */
function initCatalogControls() {
    const searchInput = document.getElementById("product-search");
    const stockFilter = document.getElementById("product-stock-filter");
    const sortSelect = document.getElementById("product-sort");

    searchInput?.addEventListener("input", () => {
        applyCatalogFilters();
    });

    stockFilter?.addEventListener("change", () => {
        applyCatalogFilters();
    });

    sortSelect?.addEventListener("change", () => {
        applyCatalogFilters();
    });
}

async function refreshProductsUI() {
    catalogProducts = await fetchProducts();

    applyCatalogFilters();
}

// =============================================================================
//  CARRITO
// =============================================================================

async function getServerCart() {
    try {
        const res = await fetch(api.cartGet, {
            credentials: "include",
        });

        if (!res.ok) return null;

        return await res.json();
    } catch {
        return null;
    }
}

function getLocalCart() {
    try {
        return JSON.parse(localStorage.getItem("cart") || "{}");
    } catch {
        return {};
    }
}

function saveLocalCart(cart) {
    localStorage.setItem("cart", JSON.stringify(cart));
}

/*
 * Nombre: addToCart
 * Descripcion: Agrega un producto al carrito usando primero el backend y luego localStorage como respaldo.
 */
async function addToCart(productId, qty = 1) {
    try {
        const res = await fetch(api.cartAdd, {
            method: "POST",
            headers: csrfHeaders(),
            credentials: "include",
            body: JSON.stringify({ productId, quantity: qty }),
        });

        if (res.ok) {
            await updateCartUI();

            showToast("Producto agregado al carrito.", "success");

            return;
        }

        console.error("addToCart fallo en servidor:", res.status, await res.text());
    } catch (err) {
        console.warn("addToCart error de red:", err);
    }

    const cart = getLocalCart();

    cart[productId] = (cart[productId] || 0) + qty;

    saveLocalCart(cart);

    await updateCartUI();

    showToast("Producto agregado al carrito.", "success");
}

async function decreaseCartItem(productId) {
    try {
        const res = await fetch(api.cartDecrease, {
            method: "POST",
            headers: csrfHeaders(),
            credentials: "include",
            body: JSON.stringify({ productId }),
        });

        if (res.ok) {
            await updateCartUI();

            return;
        }

        console.error("decreaseCartItem fallo:", res.status, await res.text());
    } catch (err) {
        console.warn("decreaseCartItem error de red:", err);
    }
}

async function removeFromCart(productId) {
    try {
        const res = await fetch(api.cartRemove, {
            method: "POST",
            headers: csrfHeaders(),
            credentials: "include",
            body: JSON.stringify({ productId }),
        });

        if (res.ok) {
            await updateCartUI();

            return;
        }

        console.error("removeFromCart fallo:", res.status, await res.text());
    } catch (err) {
        console.warn("removeFromCart error de red:", err);
    }

    const cart = getLocalCart();

    delete cart[productId];

    saveLocalCart(cart);

    await updateCartUI();
}

/*
 * Nombre: updateCartUI
 * Descripcion: Actualiza productos, cantidades, botones, contador y total del carrito.
 */
async function updateCartUI() {
    const itemsEl = document.getElementById("cart-items");
    const countEl = document.getElementById("cart-count");
    const totalEl = document.getElementById("cart-total");

    if (!itemsEl || !countEl || !totalEl) return;

    let items = [];

    const serverCart = await getServerCart();

    if (serverCart && Array.isArray(serverCart.items)) {
        items = serverCart.items;
    } else {
        const local = getLocalCart();
        const ids = Object.keys(local).map(Number);

        if (ids.length > 0) {
            const products = await fetchProducts();

            items = ids.map((id) => {
                const product = products.find((p) => p.id === id) || {
                    id,
                    name: "Producto",
                    price: 0,
                    image: "/static/store/img/placeholder.png",
                };

                return { product, quantity: local[id] };
            });
        }
    }

    if (!items.length) {
        itemsEl.innerHTML = `
            <div class="empty-cart">
                <div class="empty-cart-icon">Carrito</div>

                <h3>Tu carrito está vacío</h3>

                <p>
                    Agrega productos para comenzar tu compra.
                </p>

                <button class="btn empty-cart-btn">
                    Ver productos
                </button>
            </div>
        `;

        document
            .querySelector(".empty-cart-btn")
            ?.addEventListener("click", () => {
                const cartDrawer = document.getElementById("cart-drawer");
                const cartToggle = document.getElementById("cart-toggle");

                closeModalSafely(cartDrawer, cartToggle);

                document
                    .getElementById("productos")
                    ?.scrollIntoView({
                        behavior: "smooth",
                    });
            });

        countEl.textContent = "0";
        totalEl.textContent = "$0.00";

        return;
    }

    itemsEl.innerHTML = items
        .map((item) => {
            const isMaxStock = Number(item.quantity) >= Number(item.product.stock || 0);

            return `
                <div class="cart-item" data-id="${item.product.id}">
                    <img
                        src="${escapeHtml(item.product.image || "/static/store/img/placeholder.png")}"
                        alt="${escapeHtml(item.product.name)}"
                    />

                    <div class="cart-item-info">
                        <strong>${escapeHtml(item.product.name)}</strong>
                        <small>$${Number(item.product.price).toFixed(2)} x ${item.quantity}</small>
                    </div>

                    <div class="cart-item-actions">
                        <button class="btn small decrease-item" data-id="${item.product.id}">
                            -
                        </button>

                        <span class="cart-qty">${item.quantity}</span>

                        <button
                            class="btn small increase-item"
                            data-id="${item.product.id}"
                            ${isMaxStock ? "disabled" : ""}
                        >
                            +
                        </button>

                        <button class="btn small remove-item" data-id="${item.product.id}">
                            Eliminar
                        </button>
                    </div>
                </div>
            `;
        })
        .join("");

    document.querySelectorAll(".remove-item").forEach((btn) => {
        btn.addEventListener("click", () => removeFromCart(Number(btn.dataset.id)));
    });

    document.querySelectorAll(".increase-item").forEach((btn) => {
        btn.addEventListener("click", () => addToCart(Number(btn.dataset.id), 1));
    });

    document.querySelectorAll(".decrease-item").forEach((btn) => {
        btn.addEventListener("click", () => decreaseCartItem(Number(btn.dataset.id)));
    });

    const total = items.reduce(
        (sum, item) => sum + Number(item.product.price) * Number(item.quantity),
        0
    );

    const count = items.reduce(
        (sum, item) => sum + Number(item.quantity),
        0
    );

    countEl.textContent = String(count);
    totalEl.textContent = `$${total.toFixed(2)}`;
}

// =============================================================================
//  INICIALIZACION Y EVENTOS DE INTERFAZ
// =============================================================================

/*
 * Nombre: Modulo de inicializacion y eventos de interfaz
 * Descripcion: Conecta los elementos del DOM con las funciones principales cuando la pagina termina de cargar.
 */
document.addEventListener("DOMContentLoaded", async () => {
    await refreshAuthState();

    renderProductsSkeleton();

    catalogProducts = await fetchProducts();

    initCatalogControls();

    applyCatalogFilters();

await updateCartUI();

    const cartToggle = document.getElementById("cart-toggle");
    const cartDrawer = document.getElementById("cart-drawer");
    const cartClose = document.getElementById("cart-close");

    cartToggle?.addEventListener("click", () => {
        clearCartFeedback();

        cartDrawer?.setAttribute("aria-hidden", "false");
        cartDrawer?.classList.add("open");
    });

    cartClose?.addEventListener("click", () => {
        closeModalSafely(cartDrawer, cartToggle);
    });

    const authModal = document.getElementById("auth-modal");
    const btnOpenAuth = document.getElementById("open-auth");
    const btnLogout = document.getElementById("logout-btn");
    const authClose = document.getElementById("auth-close");
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");

    btnOpenAuth?.addEventListener("click", () => {
        clearAuthFeedback();

        authModal?.setAttribute("aria-hidden", "false");
        authModal?.classList.add("open");
    });

    authClose?.addEventListener("click", () => {
        closeModalSafely(authModal, btnOpenAuth);
    });

    document.getElementById("show-register")?.addEventListener("click", (e) => {
        e.preventDefault();

        clearAuthFeedback();

        if (loginForm) loginForm.style.display = "none";
        if (registerForm) registerForm.style.display = "block";
    });

    document.getElementById("show-login")?.addEventListener("click", (e) => {
        e.preventDefault();

        clearAuthFeedback();

        if (loginForm) loginForm.style.display = "block";
        if (registerForm) registerForm.style.display = "none";
    });

    loginForm?.addEventListener("submit", async (e) => {
        e.preventDefault();

        clearAuthFeedback();

        const emailOrUser = document.getElementById("login-email")?.value || "";
        const password = document.getElementById("login-password")?.value || "";

        if (isEmpty(emailOrUser)) {
            showAuthFeedback("Ingresa tu correo o usuario.", "error");
            return;
        }

        if (isEmpty(password)) {
            showAuthFeedback("Ingresa tu contrasena.", "error");
            return;
        }

        try {
            await loginUser(emailOrUser, password);

            closeModalSafely(authModal, btnOpenAuth);

            await refreshAuthState();
            await updateCartUI();
        } catch {
            showAuthFeedback("No se pudo iniciar sesion. Verifica tus datos.", "error");
        }
    });

    registerForm?.addEventListener("submit", async (e) => {
        e.preventDefault();

        clearAuthFeedback();

        const name = document.getElementById("reg-name")?.value || "";
        const email = document.getElementById("reg-email")?.value || "";
        const password = document.getElementById("reg-password")?.value || "";

        if (isEmpty(name)) {
            showAuthFeedback("Ingresa un nombre de usuario.", "error");
            return;
        }

        if (isEmpty(email)) {
            showAuthFeedback("Ingresa un correo electronico.", "error");
            return;
        }

        if (!isValidEmail(email)) {
            showAuthFeedback("Ingresa un correo valido.", "error");
            return;
        }

        if (isEmpty(password)) {
            showAuthFeedback("Ingresa una contrasena.", "error");
            return;
        }

        if (password.length < 6) {
            showAuthFeedback("La contrasena debe tener al menos 6 caracteres.", "error");
            return;
        }

        try {
            await registerUser(name, email, password);

            showAuthFeedback("Cuenta creada correctamente.", "success");

            setTimeout(async () => {
                closeModalSafely(authModal, btnOpenAuth);

                await refreshAuthState();
                await updateCartUI();
            }, 800);
        } catch (err) {
            showAuthFeedback(err.message || "No se pudo registrar la cuenta.", "error");
        }
    });

    btnLogout?.addEventListener("click", async () => {
        await logoutUser();
    });

    const myOrdersBtn = document.getElementById("my-orders-btn");
    const ordersModal = document.getElementById("orders-modal");
    const ordersClose = document.getElementById("orders-close");

    myOrdersBtn?.addEventListener("click", async () => {
        ordersModal?.setAttribute("aria-hidden", "false");
        ordersModal?.classList.add("open");

        clearOrdersFeedback();

        try {
            const data = await fetchMyOrders();

            renderMyOrders(data);
        } catch {
            const body = document.getElementById("orders-body");

            if (body) {
                body.innerHTML = `<p class="muted">Error cargando pedidos.</p>`;
            }

            showOrdersFeedback("No se pudieron cargar los pedidos.", "error");
        }
    });

    ordersClose?.addEventListener("click", () => {
        hideOrderCancelConfirm();

        closeModalSafely(ordersModal, myOrdersBtn);
    });

    const ordersConfirmYes = document.getElementById("orders-confirm-yes");
    const ordersConfirmNo = document.getElementById("orders-confirm-no");

    ordersConfirmNo?.addEventListener("click", () => {
        hideOrderCancelConfirm();
    });

    ordersConfirmYes?.addEventListener("click", async () => {
        if (!pendingCancelOrderId || !pendingCancelButton) return;

        const orderId = pendingCancelOrderId;
        const btn = pendingCancelButton;
        const originalText = btn.textContent;

        clearOrdersFeedback();
        hideOrderCancelConfirm();

        try {
            btn.disabled = true;
            btn.textContent = "Cancelando...";

            const result = await cancelOrder(orderId);
            const updatedData = await fetchMyOrders();

            renderMyOrders(updatedData);

            await refreshProductsUI();

            showOrdersFeedback(
                result.message || `Pedido #${orderId} cancelado correctamente.`,
                "success"
            );

            showToast("Pedido cancelado correctamente.", "success");
        } catch (err) {
            btn.disabled = false;
            btn.textContent = originalText;

            showOrdersFeedback(
                err.message || "No se pudo cancelar el pedido.",
                "error"
            );
        }
    });

    const checkoutBtn = document.getElementById("checkout-btn");

    checkoutBtn?.addEventListener("click", async () => {
        const originalText = checkoutBtn.textContent;

        const serverCart = await getServerCart();
        const localCart = getLocalCart();

        const hasServerItems =
            serverCart &&
            Array.isArray(serverCart.items) &&
            serverCart.items.length > 0;

        const hasLocalItems =
            localCart &&
            Object.keys(localCart).length > 0;

        if (!hasServerItems && !hasLocalItems) {
            showCartFeedback("Tu carrito esta vacio.", "error");
            return;
        }

        try {
            checkoutBtn.disabled = true;
            checkoutBtn.textContent = "Procesando...";

            const res = await fetch(api.checkout, {
                method: "POST",
                headers: csrfHeaders(),
                credentials: "include",
            });

            if (!res.ok) {
                let msg = "Error en el pago. Intenta nuevamente.";

                try {
                    const data = await res.json();

                    msg = data?.error || data?.detail || data?.message || msg;
                } catch {
                    // Se conserva el mensaje por defecto.
                }

                if (res.status === 401 || res.status === 403) {
                    msg = "Inicia sesion para pagar";
                    btnOpenAuth?.click();
                }

                showCartFeedback(msg, "error");

                return;
            }

            const okData = await res.json();

            showCartFeedback(
                okData?.message || "Compra realizada con exito",
                "success"
            );

            showToast("Compra realizada con exito.", "success");

            localStorage.removeItem("cart");

            await updateCartUI();
            await refreshProductsUI();

            closeModalSafely(cartDrawer, cartToggle);
        } catch {
            showCartFeedback("Error en el pago. Intenta nuevamente.", "error");
        } finally {
            checkoutBtn.disabled = false;
            checkoutBtn.textContent = originalText;
        }
    });
});