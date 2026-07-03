/*
 * Archivo: app.js
 * Descripcion: Archivo principal del frontend encargado de productos, autenticacion, carrito, pedidos, checkout, feedback visual y eventos de interfaz.
 * Dependencias: Django templates, endpoints REST del backend, localStorage, DOM API, Fetch API, style.css
 */

// =============================================================================
//  ENDPOINTS DE LA API
// =============================================================================

const api = {
    categories: "/api/categories/",
    products: "/api/products/",
    authRegister: "/api/auth/register/",
    authLogin: "/api/auth/login/",
    authPasswordResetRequest: "/api/auth/password-reset/request/",
    authPasswordResetConfirm: "/api/auth/password-reset/confirm/",
    authLogout: "/api/auth/logout/",
    me: "/api/auth/me/",
    authProfile: "/api/auth/profile/",
    authPasswordChange: "/api/auth/password-change/",
    shippingAddresses: "/api/auth/shipping-addresses/",
    cartGet: "/api/cart/",
    cartAdd: "/api/cart/add/",
    cartUpdate: "/api/cart/update/",
    cartDecrease: "/api/cart/decrease/",
    cartRemove: "/api/cart/remove/",
    cartClear: "/api/cart/clear/",
    cartApplyCoupon: "/api/cart/apply-coupon/",
    cartRemoveCoupon: "/api/cart/remove-coupon/",
    checkout: "/api/orders/checkout/",
    myOrders: "/api/orders/my/",
    contact: "/api/contact/",
    favorites: "/api/favorites/",
    toggleFavorite: "/api/favorites/toggle/",

    orderDetail: (orderId) => `/api/orders/${orderId}/`,
    reorderOrder: (orderId) => `/api/orders/reorder/${orderId}/`,
    cancelOrder: (orderId) => `/api/orders/cancel/${orderId}/`,
    shippingAddressDetail: (addressId) => `/api/auth/shipping-addresses/${addressId}/`,
    productReviews: (productId) => `/api/products/${productId}/reviews/`,
    submitProductReview: (productId) => `/api/products/${productId}/reviews/submit/`,
};

const shippingLimits = {
    name: 150,
    phone: 30,
    address: 200,
    city: 100,
    notes: 500,
};

const shippingPhonePattern = /^[0-9\s()+-]+$/;
const checkoutIdempotencyStorageKey = "checkout_idempotency";
const authPasswordMinLength = 12;

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

function sanitizeExternalUrl(value) {
    const rawUrl = String(value || "").trim();

    if (!rawUrl) return "";

    try {
        const parsedUrl = new URL(rawUrl, window.location.origin);

        if (!["http:", "https:"].includes(parsedUrl.protocol)) {
            return "";
        }

        return parsedUrl.href;
    } catch {
        return "";
    }
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

function getCsrfToken() {
    const metaToken = document
        .querySelector('meta[name="csrf-token"]')
        ?.getAttribute("content");

    return metaToken || getCookie("csrftoken");
}

/*
 * Nombre: csrfHeaders
 * Descripcion: Construye los encabezados necesarios para enviar JSON y token CSRF al backend Django.
 */
function csrfHeaders() {
    const headers = {
        "Content-Type": "application/json",
    };
    const csrfToken = getCsrfToken();

    if (csrfToken) {
        headers["X-CSRFToken"] = csrfToken;
    }

    return headers;
}

/*
 * Nombre: generateCheckoutIdempotencyKey
 * Descripcion: Genera una clave UUID para identificar un intento unico de checkout.
 */
function generateCheckoutIdempotencyKey() {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }

    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
        const random = Math.floor(Math.random() * 16);
        const value = char === "x" ? random : (random & 0x3) | 0x8;

        return value.toString(16);
    });
}

/*
 * Nombre: buildCheckoutCartFingerprint
 * Descripcion: Resume productos y cantidades para renovar la clave cuando cambia el carrito.
 */
function buildCheckoutCartFingerprint(serverCart, localCart) {
    let entries = [];

    if (Array.isArray(serverCart?.items) && serverCart.items.length) {
        entries = serverCart.items.map((item) => [
            String(item.product?.id || ""),
            Number(item.quantity || 0),
        ]);
    } else {
        entries = Object.entries(localCart || {}).map(([productId, quantity]) => [
            String(productId),
            Number(quantity || 0),
        ]);
    }

    entries.sort((first, second) => first[0].localeCompare(second[0]));

    return JSON.stringify(entries);
}

/*
 * Nombre: getCheckoutIdempotencyKey
 * Descripcion: Reutiliza la clave del mismo carrito o crea una nueva.
 */
function getCheckoutIdempotencyKey(cartFingerprint) {
    try {
        const storedValue = sessionStorage.getItem(checkoutIdempotencyStorageKey);
        const storedData = storedValue ? JSON.parse(storedValue) : null;

        if (
            storedData?.key &&
            storedData?.cartFingerprint === cartFingerprint
        ) {
            return storedData.key;
        }
    } catch {
        // Si sessionStorage falla, se crea una clave nueva para este intento.
    }

    const key = generateCheckoutIdempotencyKey();

    try {
        sessionStorage.setItem(
            checkoutIdempotencyStorageKey,
            JSON.stringify({key, cartFingerprint})
        );
    } catch {
        // El checkout puede continuar aunque sessionStorage no este disponible.
    }

    return key;
}

/*
 * Nombre: clearCheckoutIdempotencyKey
 * Descripcion: Elimina la clave una vez confirmada la compra.
 */
function clearCheckoutIdempotencyKey() {
    try {
        sessionStorage.removeItem(checkoutIdempotencyStorageKey);
    } catch {
        // No se requiere accion adicional.
    }
}

function isEmpty(value) {
    return !value || value.trim() === "";
}

function getShippingValidationError(shippingData) {
    const phoneDigits = shippingData.shippingPhone.replace(/\D/g, "");

    if (
        !shippingData.shippingName ||
        !shippingData.shippingPhone ||
        !shippingData.shippingAddress ||
        !shippingData.shippingCity
    ) {
        return "Completa nombre, telefono, direccion y ciudad.";
    }

    if (shippingData.shippingName.length > shippingLimits.name) {
        return "El nombre de envio es demasiado largo.";
    }

    if (shippingData.shippingPhone.length > shippingLimits.phone) {
        return "El telefono de envio es demasiado largo.";
    }

    if (
        !shippingPhonePattern.test(shippingData.shippingPhone) ||
        phoneDigits.length < 7 ||
        phoneDigits.length > 15
    ) {
        return "Ingresa un telefono de envio valido.";
    }

    if (shippingData.shippingAddress.length > shippingLimits.address) {
        return "La direccion de envio es demasiado larga.";
    }

    if (shippingData.shippingCity.length > shippingLimits.city) {
        return "La ciudad de envio es demasiado larga.";
    }

    if (shippingData.shippingNotes.length > shippingLimits.notes) {
        return "Las notas de envio son demasiado largas.";
    }

    return "";
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function normalizeStatus(status) {
    return (status || "pendiente").toLowerCase().trim();
}

function formatOrderStatus(order) {
    const statusNorm = normalizeStatus(order?.status);

    const labels = {
        pendiente: "Pendiente",
        pagado: "Pagado",
        en_preparacion: "En preparacion",
        enviado: "Enviado",
        entregado: "Entregado",
        cancelado: "Cancelado",
        reembolsado: "Reembolsado",
    };

    return order?.status_label || labels[statusNorm] || statusNorm;
}

// =============================================================================
//  VERIFICACION DE EDAD
// =============================================================================

const AGE_VERIFICATION_KEY = "vapeShopAgeVerified";
let ageVerifiedInSession = false;
let currentUser = null;

/*
 * Nombre: hasAgeVerification
 * Descripcion: Comprueba si el usuario ya confirmo que cumple con la edad legal requerida.
 * Retorna: true si la confirmacion esta guardada, false en caso contrario.
 */
function hasAgeVerification() {
    if (ageVerifiedInSession) return true;

    try {
        return localStorage.getItem(AGE_VERIFICATION_KEY) === "true";
    } catch {
        return false;
    }
}

/*
 * Nombre: showAgeVerification
 * Descripcion: Muestra el modal obligatorio de verificacion de edad.
 */
function showAgeVerification() {
    const modal = document.getElementById("age-verification-modal");
    const confirmBtn = document.getElementById("age-confirm-btn");

    if (!modal) return;

    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("open");
    document.body.classList.add("age-verification-locked");

    requestAnimationFrame(() => {
        confirmBtn?.focus();
    });
}

/*
 * Nombre: hideAgeVerification
 * Descripcion: Cierra el modal de verificacion de edad y libera la navegacion.
 */
function hideAgeVerification() {
    const modal = document.getElementById("age-verification-modal");
    const feedback = document.getElementById("age-verification-feedback");

    if (!modal) return;

    if (feedback) {
        feedback.textContent = "";
    }

    modal.setAttribute("aria-hidden", "true");
    modal.classList.remove("open");
    document.body.classList.remove("age-verification-locked");
}

/*
 * Nombre: confirmAgeVerification
 * Descripcion: Guarda la confirmacion de mayoria de edad y permite usar la tienda.
 */
function confirmAgeVerification() {
    ageVerifiedInSession = true;

    try {
        localStorage.setItem(AGE_VERIFICATION_KEY, "true");
    } catch {
        // Si localStorage no esta disponible, la confirmacion se conserva solo en la sesion actual.
    }

    hideAgeVerification();
    showToast("Verificacion de edad confirmada.", "success");
}

/*
 * Nombre: denyAgeVerification
 * Descripcion: Mantiene bloqueado el acceso cuando el usuario no confirma la edad requerida.
 */
function denyAgeVerification() {
    const feedback = document.getElementById("age-verification-feedback");

    ageVerifiedInSession = false;

    try {
        localStorage.removeItem(AGE_VERIFICATION_KEY);
    } catch {
        // Se conserva el bloqueo visual aunque no se pueda modificar localStorage.
    }

    if (feedback) {
        feedback.textContent = "No puedes continuar sin confirmar que cumples con la edad legal requerida.";
    }
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

function showProfileFeedback(message, type = "success") {
    const feedback = document.getElementById("profile-feedback");

    if (!feedback) return;

    feedback.textContent = message;
    feedback.className = `auth-feedback ${type}`;
    feedback.style.display = "block";
}

function clearProfileFeedback() {
    const feedback = document.getElementById("profile-feedback");

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

function showFavoritesFeedback(message, type = "success") {
    const feedback = document.getElementById("favorites-feedback");

    if (!feedback) return;

    feedback.textContent = message;
    feedback.className = `orders-feedback ${type}`;
    feedback.style.display = "block";
}

function clearFavoritesFeedback() {
    const feedback = document.getElementById("favorites-feedback");

    if (!feedback) return;

    feedback.textContent = "";
    feedback.className = "orders-feedback";
    feedback.style.display = "none";
}

function showContactFeedback(message, type = "success") {
    const feedback = document.getElementById("contact-feedback");

    if (!feedback) return;

    feedback.textContent = message;
    feedback.className = `contact-feedback ${type}`;
    feedback.style.display = "block";
}

function clearContactFeedback() {
    const feedback = document.getElementById("contact-feedback");

    if (!feedback) return;

    feedback.textContent = "";
    feedback.className = "contact-feedback";
    feedback.style.display = "none";
}

/*
 * Nombre: showCheckoutSuccess
 * Descripcion: Muestra el modal de resumen cuando una compra se completa correctamente.
 */
function showCheckoutSuccess(data) {
    const modal = document.getElementById("checkout-success-modal");
    const orderEl = document.getElementById("checkout-success-order");
    const totalEl = document.getElementById("checkout-success-total");

    if (!modal) return;

    const orderId = data?.order_id || "---";
    const total = Number(data?.total_pagado || 0);

    if (orderEl) {
        orderEl.textContent = `#${orderId}`;
    }

    if (totalEl) {
        totalEl.textContent = `$${total.toFixed(2)}`;
    }

    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("open");
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
    const btnProfile = document.getElementById("profile-btn");
    const btnMyOrders = document.getElementById("my-orders-btn");
    const btnFavorites = document.getElementById("favorites-btn");

    if (btnLogin) btnLogin.style.display = isLoggedIn ? "none" : "inline-flex";
    if (btnLogout) btnLogout.style.display = isLoggedIn ? "inline-flex" : "none";
    if (btnProfile) btnProfile.style.display = isLoggedIn ? "inline-flex" : "none";
    if (btnMyOrders) btnMyOrders.style.display = isLoggedIn ? "inline-flex" : "none";
    if (btnFavorites) btnFavorites.style.display = isLoggedIn ? "inline-flex" : "none";

    currentUser = isLoggedIn ? user : null;
    renderShippingAddressBook();

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
 * Nombre: requestPasswordReset
 * Descripcion: Solicita al backend el envio de un enlace para recuperar la cuenta.
 */
async function requestPasswordReset(email) {
    const res = await fetch(api.authPasswordResetRequest, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify({ email }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
        throw new Error(
            data?.error ||
            data?.detail ||
            data?.message ||
            "No se pudo solicitar la recuperacion."
        );
    }

    return data;
}

/*
 * Nombre: confirmPasswordReset
 * Descripcion: Confirma el token de recuperacion y guarda una nueva contrasena.
 */
async function confirmPasswordReset(uid, token, password, passwordConfirm) {
    const res = await fetch(api.authPasswordResetConfirm, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify({
            uid,
            token,
            password,
            password_confirm: passwordConfirm,
        }),
    });
    const data = await res.json().catch(() => ({}));
    const passwordError = Array.isArray(data?.password)
        ? data.password[0]
        : data?.password;

    if (!res.ok) {
        throw new Error(
            passwordError ||
            data?.error ||
            data?.detail ||
            data?.message ||
            "No se pudo actualizar la contrasena."
        );
    }

    return data;
}

async function updateProfile(profileData) {
    const res = await fetch(api.authProfile, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify(profileData),
    });
    const data = await res.json();

    if (!res.ok) {
        const firstNameError = Array.isArray(data?.first_name)
            ? data.first_name[0]
            : data?.first_name;
        const lastNameError = Array.isArray(data?.last_name)
            ? data.last_name[0]
            : data?.last_name;
        const phoneError = Array.isArray(data?.phone)
            ? data.phone[0]
            : data?.phone;

        throw new Error(
            firstNameError ||
            lastNameError ||
            phoneError ||
            data?.error ||
            "No se pudo actualizar el perfil."
        );
    }

    return data;
}

async function changePassword(passwordData) {
    const res = await fetch(api.authPasswordChange, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify(passwordData),
    });
    const data = await res.json().catch(() => ({}));
    const passwordError = Array.isArray(data?.password)
        ? data.password[0]
        : data?.password;

    if (!res.ok) {
        throw new Error(
            passwordError ||
            data?.error ||
            data?.detail ||
            data?.message ||
            "No se pudo actualizar la contrasena."
        );
    }

    return data;
}

function getShippingAddressApiError(data) {
    const fields = ["label", "name", "phone", "address", "city", "notes"];

    for (const field of fields) {
        const value = data?.[field];

        if (Array.isArray(value) && value.length) return value[0];
        if (value) return value;
    }

    return data?.error || data?.detail || data?.message || "";
}

async function saveShippingAddress(addressData, addressId = null) {
    const url = addressId
        ? api.shippingAddressDetail(addressId)
        : api.shippingAddresses;
    const method = addressId ? "PATCH" : "POST";
    const res = await fetch(url, {
        method,
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify(addressData),
    });
    const data = await res.json();

    if (!res.ok) {
        throw new Error(
            getShippingAddressApiError(data) ||
            "No se pudo guardar la direccion."
        );
    }

    return data;
}

async function deleteShippingAddress(addressId) {
    const res = await fetch(api.shippingAddressDetail(addressId), {
        method: "DELETE",
        headers: csrfHeaders(),
        credentials: "include",
    });
    const data = await res.json();

    if (!res.ok) {
        throw new Error(
            data?.error ||
            data?.detail ||
            "No se pudo eliminar la direccion."
        );
    }

    return data;
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
    clearFavoritesFeedback();
    clearProfileFeedback();
    hideOrderCancelConfirm();
    closeModalSafely(document.getElementById("favorites-modal"));
    closeModalSafely(document.getElementById("profile-modal"));

    clearShippingForm();
    resetCheckoutSummary();

    await updateCartUI();
    await refreshProductsUI();
}

// =============================================================================
//  CONTACTO
// =============================================================================

/*
 * Nombre: submitContactLead
 * Descripcion: Envia los datos del formulario de contacto al backend.
 */
async function submitContactLead(contactData) {
    const res = await fetch(api.contact, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify(contactData),
    });

    const data = await res.json();

    if (!res.ok) {
        const emailError = Array.isArray(data?.email)
            ? data.email[0]
            : data?.email;
        const phoneError = Array.isArray(data?.phone)
            ? data.phone[0]
            : data?.phone;

        throw new Error(
            emailError ||
            phoneError ||
            data?.error ||
            data?.detail ||
            "No se pudo enviar el contacto."
        );
    }

    return data;
}

// =============================================================================
//  FAVORITOS
// =============================================================================

async function fetchFavorites() {
    const res = await fetch(api.favorites, {
        credentials: "include",
    });

    if (res.status === 401 || res.status === 403) {
        return { notLogged: true, favorites: [] };
    }

    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudieron cargar los favoritos");
    }

    return data;
}

async function toggleFavorite(productId) {
    const res = await fetch(api.toggleFavorite, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify({ productId }),
    });
    const data = await res.json();

    if (!res.ok) {
        const err = new Error(data?.error || "No se pudo actualizar el favorito");

        err.authRequired = res.status === 401 || res.status === 403;

        throw err;
    }

    return data;
}

function getFavoriteButtonLabel(product) {
    return product?.is_favorite
        ? "Quitar de favoritos"
        : "Agregar a favoritos";
}

function getFavoriteIcon(product) {
    return product?.is_favorite ? "♥" : "♡";
}

function renderFavoriteIconButton(product) {
    const activeClass = product?.is_favorite ? "active" : "";
    const label = getFavoriteButtonLabel(product);

    return `
        <button
            class="favorite-toggle ${activeClass}"
            type="button"
            data-favorite-id="${product.id}"
            aria-label="${label}"
            title="${label}"
        >
            <span class="favorite-icon" aria-hidden="true">${getFavoriteIcon(product)}</span>
        </button>
    `;
}

function mergeProductsIntoCatalog(products) {
    products.forEach((product) => {
        const index = catalogProducts.findIndex(
            (item) => Number(item.id) === Number(product.id)
        );

        if (index >= 0) {
            catalogProducts[index] = {
                ...catalogProducts[index],
                ...product,
            };
        } else {
            catalogProducts.push(product);
        }
    });
}

function setCatalogProductFavoriteState(productId, isFavorite) {
    catalogProducts = catalogProducts.map((product) => {
        if (Number(product.id) !== Number(productId)) return product;

        return {
            ...product,
            is_favorite: isFavorite,
        };
    });
}

function updateFavoriteButtons(productId, isFavorite) {
    document
        .querySelectorAll(`[data-favorite-id="${productId}"]`)
        .forEach((btn) => {
            const label = isFavorite
                ? "Quitar de favoritos"
                : "Agregar a favoritos";
            const icon = btn.querySelector(".favorite-icon");
            const text = btn.querySelector(".favorite-text");

            btn.classList.toggle("active", isFavorite);
            btn.setAttribute("aria-label", label);
            btn.setAttribute("title", label);

            if (icon) {
                icon.textContent = isFavorite ? "♥" : "♡";
            }

            if (text) {
                text.textContent = isFavorite ? "Favorito" : "Guardar";
            }
        });
}

async function handleFavoriteToggle(btn, productId, options = {}) {
    const originalDisabled = btn.disabled;

    btn.disabled = true;

    try {
        const result = await toggleFavorite(productId);

        setCatalogProductFavoriteState(result.product_id, result.is_favorite);
        updateFavoriteButtons(result.product_id, result.is_favorite);
        showToast(result.message || "Favoritos actualizados.", "success");

        if (options.refreshFavorites) {
            await loadAndRenderFavorites();
        }
    } catch (err) {
        if (err.authRequired) {
            showToast("Inicia sesion para guardar favoritos.", "error");
            document.getElementById("open-auth")?.click();
        } else {
            showToast(err.message || "No se pudo actualizar favoritos.", "error");
        }
    } finally {
        btn.disabled = originalDisabled;
    }
}

function renderFavorites(data) {
    const body = document.getElementById("favorites-body");

    if (!body) return;

    if (data?.notLogged) {
        body.innerHTML = `<p class="muted">Debes iniciar sesion para ver tus favoritos.</p>`;
        return;
    }

    const favorites = data?.favorites || [];

    if (!favorites.length) {
        body.innerHTML = `
            <div class="empty-orders">
                <div class="empty-orders-icon">Favoritos</div>

                <h3>Aun no tienes favoritos</h3>

                <p>Marca productos con el corazon para encontrarlos mas rapido.</p>

                <button class="btn favorites-explore-btn">
                    Explorar productos
                </button>
            </div>
        `;

        document
            .querySelector(".favorites-explore-btn")
            ?.addEventListener("click", () => {
                const modal = document.getElementById("favorites-modal");
                const favoritesBtn = document.getElementById("favorites-btn");

                closeModalSafely(modal, favoritesBtn);

                document
                    .getElementById("productos")
                    ?.scrollIntoView({
                        behavior: "smooth",
                    });
            });

        return;
    }

    mergeProductsIntoCatalog(favorites);

    body.innerHTML = `
        <div class="favorites-grid">
            ${favorites
                .map((product) => {
                    const stock = Number(product.stock || 0);
                    const addButton = stock > 0
                        ? `
                            <button class="btn small favorite-cart-btn" data-id="${product.id}">
                                Agregar
                            </button>
                        `
                        : `<button class="btn small" disabled>Sin stock</button>`;

                    return `
                        <article class="favorite-item">
                            <img
                                src="${escapeHtml(product.image) || "/static/store/img/STLTH.webp"}"
                                alt="${escapeHtml(product.name)}"
                            />

                            <div>
                                <h3>${escapeHtml(product.name)}</h3>

                                ${renderProductRating(product)}

                                <p class="muted">$${Number(product.price || 0).toFixed(2)}</p>

                                <div class="favorite-item-actions">
                                    <button class="btn small favorite-detail-btn" data-id="${product.id}">
                                        Ver detalle
                                    </button>

                                    ${addButton}

                                    <button
                                        class="btn small btn-outline favorite-remove-btn"
                                        data-favorite-id="${product.id}"
                                    >
                                        Quitar
                                    </button>
                                </div>
                            </div>
                        </article>
                    `;
                })
                .join("")}
        </div>
    `;

    document.querySelectorAll(".favorite-detail-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            openProductDetail(Number(btn.dataset.id));
        });
    });

    document.querySelectorAll(".favorite-cart-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await addToCart(Number(btn.dataset.id), 1);
        });
    });

    document.querySelectorAll(".favorite-remove-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await handleFavoriteToggle(btn, btn.dataset.favoriteId, {
                refreshFavorites: true,
            });
        });
    });
}

async function loadAndRenderFavorites() {
    const body = document.getElementById("favorites-body");

    if (body) {
        body.innerHTML = `<p class="muted">Cargando favoritos...</p>`;
    }

    clearFavoritesFeedback();

    try {
        const data = await fetchFavorites();

        renderFavorites(data);
    } catch (err) {
        showFavoritesFeedback(
            err.message || "No se pudieron cargar los favoritos.",
            "error"
        );

        if (body) {
            body.innerHTML = `<p class="muted">Error cargando favoritos.</p>`;
        }
    }
}

// =============================================================================
//  RESEÑAS
// =============================================================================

async function fetchProductReviews(productId) {
    const res = await fetch(api.productReviews(productId), {
        credentials: "include",
    });
    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudieron cargar las reseñas");
    }

    return data;
}

async function submitProductReview(productId, reviewData) {
    const res = await fetch(api.submitProductReview(productId), {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify(reviewData),
    });
    const data = await res.json();

    if (!res.ok) {
        const err = new Error(data?.error || "No se pudo guardar la reseña");

        err.authRequired = res.status === 401 || res.status === 403;

        throw err;
    }

    return data;
}

function renderProductRating(product) {
    const average = Number(product?.rating_average || 0);
    const count = Number(product?.rating_count || 0);
    const rounded = Math.round(average);
    const stars = Array.from({ length: 5 })
        .map((_, index) => {
            const star = index < rounded ? "★" : "☆";

            return `<span class="rating-star" aria-hidden="true">${star}</span>`;
        })
        .join("");
    const label = count
        ? `${average.toFixed(1)} de 5 (${count})`
        : "Sin calificaciones";

    return `
        <div
            class="product-rating"
            data-rating-product-id="${product?.id || ""}"
            aria-label="${label}"
        >
            <span class="product-rating-stars">${stars}</span>

            <span>${label}</span>
        </div>
    `;
}

function setCatalogProductReviewSummary(productId, ratingAverage, ratingCount) {
    catalogProducts = catalogProducts.map((product) => {
        if (Number(product.id) !== Number(productId)) return product;

        return {
            ...product,
            rating_average: Number(ratingAverage || 0),
            rating_count: Number(ratingCount || 0),
        };
    });
}

function updateProductRatingBadges(productId, ratingAverage, ratingCount) {
    const product = {
        id: productId,
        rating_average: ratingAverage,
        rating_count: ratingCount,
    };

    document
        .querySelectorAll(`[data-rating-product-id="${productId}"]`)
        .forEach((ratingEl) => {
            ratingEl.outerHTML = renderProductRating(product);
        });
}

function renderProductReviewsPanel(productId, data) {
    const panel = document.getElementById("product-reviews-panel");

    if (!panel) return;

    const ownReview = data?.own_review || null;
    const reviews = data?.reviews || [];
    const reviewsHtml = reviews.length
        ? reviews
            .map((review) => `
                <article class="product-review-item">
                    <div>
                        <strong>${escapeHtml(review.user || "Cliente")}</strong>

                        <span>${Number(review.rating || 0)} de 5</span>
                    </div>

                    <p>${escapeHtml(review.comment || "Sin comentario.")}</p>
                </article>
            `)
            .join("")
        : `<p class="muted">Aun no hay reseñas para este producto.</p>`;

    panel.innerHTML = `
        <div class="product-reviews-head">
            <div>
                <span class="product-detail-tag">Reseñas</span>

                <h3>Opiniones de clientes</h3>
            </div>

            ${renderProductRating({
                id: productId,
                rating_average: data?.rating_average || 0,
                rating_count: data?.rating_count || 0,
            })}
        </div>

        <form class="product-review-form">
            <div class="product-review-field">
                <label for="product-review-rating">Tu calificacion</label>

                <select id="product-review-rating" name="rating">
                    ${[5, 4, 3, 2, 1]
                        .map((rating) => `
                            <option
                                value="${rating}"
                                ${Number(ownReview?.rating || 5) === rating ? "selected" : ""}
                            >
                                ${rating} de 5
                            </option>
                        `)
                        .join("")}
                </select>
            </div>

            <div class="product-review-field">
                <label for="product-review-comment">Comentario</label>

                <textarea
                    id="product-review-comment"
                    name="comment"
                    maxlength="600"
                    rows="3"
                    placeholder="Comparte tu experiencia con este producto"
                >${escapeHtml(ownReview?.comment || "")}</textarea>
            </div>

            <button class="btn small" type="submit">
                ${ownReview ? "Actualizar reseña" : "Guardar reseña"}
            </button>
        </form>

        <div class="product-review-list">
            ${reviewsHtml}
        </div>
    `;

    panel
        .querySelector(".product-review-form")
        ?.addEventListener("submit", async (event) => {
            event.preventDefault();

            const form = event.currentTarget;
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn?.textContent || "Guardar reseña";
            const rating = form.elements.rating?.value;
            const comment = form.elements.comment?.value || "";

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Guardando...";
            }

            try {
                const result = await submitProductReview(productId, {
                    rating,
                    comment,
                });

                setCatalogProductReviewSummary(
                    productId,
                    result.rating_average,
                    result.rating_count
                );
                updateProductRatingBadges(
                    productId,
                    result.rating_average,
                    result.rating_count
                );

                const refreshed = await fetchProductReviews(productId);

                renderProductReviewsPanel(productId, refreshed);
                showToast(result.message || "Reseña guardada.", "success");
            } catch (err) {
                if (err.authRequired) {
                    showToast("Inicia sesion para escribir una reseña.", "error");
                    document.getElementById("open-auth")?.click();
                } else {
                    showToast(err.message || "No se pudo guardar la reseña.", "error");
                }
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            }
        });
}

async function loadProductReviews(productId) {
    const panel = document.getElementById("product-reviews-panel");

    if (panel) {
        panel.innerHTML = `<p class="muted">Cargando reseñas...</p>`;
    }

    try {
        const data = await fetchProductReviews(productId);

        setCatalogProductReviewSummary(
            productId,
            data.rating_average,
            data.rating_count
        );
        updateProductRatingBadges(
            productId,
            data.rating_average,
            data.rating_count
        );
        renderProductReviewsPanel(productId, data);
    } catch (err) {
        if (panel) {
            panel.innerHTML = `
                <p class="muted">
                    ${escapeHtml(err.message || "No se pudieron cargar las reseñas.")}
                </p>
            `;
        }
    }
}

// =============================================================================
//  PEDIDOS
// =============================================================================

const ordersPageSize = 4;

let ordersPagination = {
    page: 1,
    page_size: ordersPageSize,
    total: 0,
    total_pages: 0,
    has_next: false,
    has_previous: false,
};

function getOrdersStatusFilterValue() {
    const statusFilter = document.getElementById("orders-status-filter");

    return statusFilter?.value || "all";
}

/*
 * Nombre: fetchMyOrders
 * Descripcion: Obtiene los pedidos del usuario autenticado.
 */
async function fetchMyOrders(page = ordersPagination.page) {
    const params = new URLSearchParams({
        page: String(Math.max(1, Number(page || 1))),
        page_size: String(ordersPageSize),
    });
    const statusFilter = getOrdersStatusFilterValue();

    if (statusFilter !== "all") {
        params.set("status", statusFilter);
    }

    const res = await fetch(`${api.myOrders}?${params.toString()}`, {
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

async function fetchOrderDetail(orderId) {
    const res = await fetch(api.orderDetail(orderId), {
        credentials: "include",
    });

    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudo cargar el detalle del pedido");
    }

    return data;
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
 * Nombre: reorderOrder
 * Descripcion: Agrega al carrito productos disponibles de un pedido anterior.
 */
async function reorderOrder(orderId) {
    const res = await fetch(api.reorderOrder(orderId), {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
    });

    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudo repetir el pedido");
    }

    return data;
}

/*
 * Nombre: renderShippingInfo
 * Descripcion: Genera el bloque visual con los datos de envio asociados a una orden.
 */
function renderShippingInfo(order) {
    const shipping = order.shipping || {};

    const hasShippingData =
        shipping.name ||
        shipping.phone ||
        shipping.address ||
        shipping.city ||
        shipping.notes;

    if (!hasShippingData) {
        return "";
    }

    return `
        <div class="order-shipping">
            <h4>Datos de envío</h4>

            <div class="order-shipping-grid">
                <p>
                    <strong>Nombre:</strong>
                    ${escapeHtml(shipping.name || "No registrado")}
                </p>

                <p>
                    <strong>Teléfono:</strong>
                    ${escapeHtml(shipping.phone || "No registrado")}
                </p>

                <p>
                    <strong>Dirección:</strong>
                    ${escapeHtml(shipping.address || "No registrada")}
                </p>

                <p>
                    <strong>Ciudad:</strong>
                    ${escapeHtml(shipping.city || "No registrada")}
                </p>

                ${shipping.notes
            ? `
                            <p class="order-shipping-notes">
                                <strong>Notas:</strong>
                                ${escapeHtml(shipping.notes)}
                            </p>
                        `
            : ""
        }
            </div>
        </div>
    `;
}

function renderTrackingInfo(order) {
    const tracking = order.tracking || {};
    const trackingUrl = sanitizeExternalUrl(tracking.url);
    const shippedAt = tracking.shipped_at
        ? new Date(tracking.shipped_at).toLocaleString()
        : "";
    const deliveredAt = tracking.delivered_at
        ? new Date(tracking.delivered_at).toLocaleString()
        : "";
    const hasTrackingData =
        tracking.carrier ||
        tracking.number ||
        trackingUrl ||
        shippedAt ||
        deliveredAt;

    if (!hasTrackingData) {
        return "";
    }

    return `
        <div class="order-tracking">
            <h4>Seguimiento del envio</h4>

            <div class="order-shipping-grid">
                ${tracking.carrier
                    ? `
                        <p>
                            <strong>Transportadora:</strong>
                            ${escapeHtml(tracking.carrier)}
                        </p>
                    `
                    : ""
                }

                ${tracking.number
                    ? `
                        <p>
                            <strong>Guia:</strong>
                            ${escapeHtml(tracking.number)}
                        </p>
                    `
                    : ""
                }

                ${shippedAt
                    ? `
                        <p>
                            <strong>Enviado:</strong>
                            ${escapeHtml(shippedAt)}
                        </p>
                    `
                    : ""
                }

                ${deliveredAt
                    ? `
                        <p>
                            <strong>Entregado:</strong>
                            ${escapeHtml(deliveredAt)}
                        </p>
                    `
                    : ""
                }

                ${trackingUrl
                    ? `
                        <p class="order-shipping-notes">
                            <strong>Rastreo:</strong>
                            <a href="${escapeHtml(trackingUrl)}" target="_blank" rel="noopener noreferrer">
                                Abrir enlace de seguimiento
                            </a>
                        </p>
                    `
                    : ""
                }
            </div>
        </div>
    `;
}

/*
 * Nombre: renderOrderTimeline
 * Descripcion: Genera una linea visual de progreso segun el estado actual de una orden.
 */
function renderOrderTimeline(order) {
    const statusNorm = normalizeStatus(order.status);

    if (statusNorm === "cancelado" || statusNorm === "reembolsado") {
        const label = statusNorm === "reembolsado"
            ? "Pedido reembolsado"
            : "Pedido cancelado";

        return `
            <div class="order-timeline cancelled">
                <div class="order-timeline-cancelled">
                    ${label}
                </div>
            </div>
        `;
    }

    const steps = [
        {
            key: "pendiente",
            label: "Pendiente",
        },
        {
            key: "pagado",
            label: "Pagado",
        },
        {
            key: "en_preparacion",
            label: "Preparacion",
        },
        {
            key: "enviado",
            label: "Enviado",
        },
        {
            key: "entregado",
            label: "Entregado",
        },
    ];

    const currentIndex = steps.findIndex((step) => step.key === statusNorm);
    const safeCurrentIndex = currentIndex >= 0 ? currentIndex : 0;

    const stepsHtml = steps
        .map((step, index) => {
            const isActive = index <= safeCurrentIndex;
            const isCurrent = index === safeCurrentIndex;

            return `
                <div class="order-timeline-step ${isActive ? "active" : ""} ${isCurrent ? "current" : ""}">
                    <span class="order-timeline-dot"></span>
                    <span class="order-timeline-label">${escapeHtml(step.label)}</span>
                </div>
            `;
        })
        .join("");

    return `
        <div class="order-timeline">
            ${stepsHtml}
        </div>
    `;
}

function renderOrderStatusHistory(order) {
    const history = Array.isArray(order?.status_history)
        ? order.status_history
        : [];

    if (!history.length) return "";

    const items = history
        .map((entry) => {
            const dateStr = entry.created_at
                ? new Date(entry.created_at).toLocaleString()
                : "";

            return `
                <li class="order-status-history-item">
                    <span class="order-status-history-dot"></span>

                    <div>
                        <strong>${escapeHtml(entry.status_label || entry.status || "Estado")}</strong>

                        <p>
                            ${escapeHtml(entry.note || "Estado actualizado.")}
                        </p>

                        <small>
                            ${escapeHtml(dateStr)}
                            ${entry.changed_by ? ` - ${escapeHtml(entry.changed_by)}` : ""}
                        </small>
                    </div>
                </li>
            `;
        })
        .join("");

    return `
        <section class="order-status-history">
            <h4>Historial de seguimiento</h4>

            <ul>
                ${items}
            </ul>
        </section>
    `;
}

async function loadAndRenderOrders(page = ordersPagination.page) {
    const data = await fetchMyOrders(page);
    const pagination = data?.pagination || {};

    ordersPagination = {
        page: Number(pagination.page || page || 1),
        page_size: Number(pagination.page_size || ordersPageSize),
        total: Number(pagination.total || 0),
        total_pages: Number(pagination.total_pages || 0),
        has_next: Boolean(pagination.has_next),
        has_previous: Boolean(pagination.has_previous),
    };

    if (
        ordersPagination.total_pages > 0 &&
        ordersPagination.page > ordersPagination.total_pages
    ) {
        return await loadAndRenderOrders(ordersPagination.total_pages);
    }

    renderMyOrders(data);
    renderOrdersPagination(ordersPagination);

    return data;
}

async function goToOrdersPage(page) {
    ordersPagination.page = Math.max(1, Number(page || 1));
    hideOrderDetailPanel();

    await loadAndRenderOrders(ordersPagination.page);
}

function renderOrdersPagination(pagination) {
    const paginationEl = document.getElementById("orders-pagination");

    if (!paginationEl) return;

    const totalPages = Number(pagination.total_pages || 0);
    const currentPage = Number(pagination.page || 1);

    if (totalPages <= 1) {
        paginationEl.innerHTML = "";
        paginationEl.setAttribute("hidden", "hidden");
        return;
    }

    paginationEl.removeAttribute("hidden");
    paginationEl.innerHTML = `
        <button
            class="orders-page-btn"
            type="button"
            data-page="${currentPage - 1}"
            ${pagination.has_previous ? "" : "disabled"}
        >
            Anterior
        </button>

        <span class="orders-page-status">
            Pagina ${currentPage} de ${totalPages}
        </span>

        <button
            class="orders-page-btn"
            type="button"
            data-page="${currentPage + 1}"
            ${pagination.has_next ? "" : "disabled"}
        >
            Siguiente
        </button>
    `;

    paginationEl.querySelectorAll(".orders-page-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await goToOrdersPage(btn.dataset.page);
        });
    });
}

function hideOrderDetailPanel() {
    const panel = document.getElementById("orders-detail");

    if (!panel) return;

    panel.setAttribute("hidden", "hidden");
    panel.innerHTML = "";
}

function renderOrderDetailPanel(order) {
    const panel = document.getElementById("orders-detail");

    if (!panel || !order) return;

    const fechaStr = order.date_ordered
        ? new Date(order.date_ordered).toLocaleString()
        : "";
    const itemsHtml = (order.items || [])
        .map((item) => `
            <div class="orders-detail-item">
                <div>
                    <strong>${escapeHtml(item.product?.name || "Producto")}</strong>

                    <span class="muted">
                        $${Number(item.product?.price || 0).toFixed(2)}
                        x ${Number(item.quantity || 0)}
                    </span>
                </div>

                <strong>$${Number(item.line_total || 0).toFixed(2)}</strong>
            </div>
        `)
        .join("");

    panel.removeAttribute("hidden");
    panel.innerHTML = `
        <div class="orders-detail-head">
            <div>
                <span class="section-eyebrow">Detalle del pedido</span>

                <h3>Pedido #${order.id}</h3>

                <p class="muted">${fechaStr}</p>
            </div>

            <button class="btn small orders-detail-close" type="button">
                Cerrar detalle
            </button>
        </div>

        ${renderOrderTimeline(order)}
        ${renderOrderStatusHistory(order)}

        <div class="orders-detail-grid">
            <section>
                <h4>Productos</h4>

                <div class="orders-detail-items">
                    ${itemsHtml || `<p class="muted">Sin productos registrados.</p>`}
                </div>
            </section>

            <section>
                <h4>Resumen</h4>

                <p>
                    <strong>Estado:</strong>
                    ${escapeHtml(formatOrderStatus(order))}
                </p>

                <p>
                    <strong>Total:</strong>
                    $${Number(order.total || 0).toFixed(2)}
                </p>
            </section>
        </div>

        ${renderShippingInfo(order)}
        ${renderTrackingInfo(order)}
    `;

    panel
        .querySelector(".orders-detail-close")
        ?.addEventListener("click", hideOrderDetailPanel);
}

/*
 * Nombre: renderMyOrders
 * Descripcion: Renderiza el historial de pedidos, estados, productos, totales y acciones disponibles.
 */
function renderMyOrders(data) {
    const body = document.getElementById("orders-body");
    const paginationEl = document.getElementById("orders-pagination");

    if (!body) return;

    hideOrderDetailPanel();

    if (data?.notLogged) {
        paginationEl?.setAttribute("hidden", "hidden");
        body.innerHTML = `<p class="muted">Debes iniciar sesion para ver tus pedidos.</p>`;
        return;
    }

    const orders = data?.orders || [];

    if (!orders.length) {
        paginationEl?.setAttribute("hidden", "hidden");
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

            const cancelButton = ["pendiente", "pagado"].includes(statusNorm)
                ? `
                    <button class="btn small cancel-order-btn" data-id="${order.id}">
                        Cancelar pedido
                    </button>
                `
                : `<span class="muted">Pedido no cancelable</span>`;

            const fechaStr = order.date_ordered
                ? new Date(order.date_ordered).toLocaleString()
                : "";

            return `
                <div class="order-card">
                    <div class="order-head">
                        <div>
                            <strong>Pedido #${order.id}</strong>

                            <span class="order-status status-${escapeHtml(statusNorm)}">
                                ${escapeHtml(formatOrderStatus(order))}
                            </span>
                        </div>

                        <div class="muted">${fechaStr}</div>
                    </div>
                    
                    ${renderOrderTimeline(order)}

                    <div class="order-items">
                        ${itemsHtml}
                    </div>

                    ${renderShippingInfo(order)}

                    <div class="order-total" style="margin-top: 10px;">
                        <span>Total</span>
                        <strong>$${Number(order.total || 0).toFixed(2)}</strong>
                    </div>

                    <div class="order-actions">
                        <button class="btn small order-detail-btn" data-id="${order.id}">
                            Ver detalle
                        </button>

                        <button class="btn small reorder-order-btn" data-id="${order.id}">
                            Comprar de nuevo
                        </button>

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

    document.querySelectorAll(".order-detail-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const originalText = btn.textContent;

            clearOrdersFeedback();

            try {
                btn.disabled = true;
                btn.textContent = "Cargando...";

                const order = await fetchOrderDetail(btn.dataset.id);

                renderOrderDetailPanel(order);
            } catch (err) {
                showOrdersFeedback(
                    err.message || "No se pudo cargar el detalle del pedido.",
                    "error"
                );
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        });
    });

    document.querySelectorAll(".reorder-order-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const originalText = btn.textContent;

            clearOrdersFeedback();

            try {
                btn.disabled = true;
                btn.textContent = "Agregando...";

                const result = await reorderOrder(btn.dataset.id);

                await updateCartUI();

                const skippedCount = Number(result.skipped_items?.length || 0);
                const message = skippedCount
                    ? "Agregamos los productos disponibles. Algunos no tenian stock."
                    : result.message || "Productos agregados al carrito.";

                showOrdersFeedback(message, skippedCount ? "error" : "success");
                showToast("Productos agregados al carrito.", "success");
            } catch (err) {
                showOrdersFeedback(
                    err.message || "No se pudo repetir el pedido.",
                    "error"
                );
                showToast("No se pudo repetir el pedido.", "error");
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        });
    });
}

// =============================================================================
//  PRODUCTOS
// =============================================================================

let catalogProducts = [];
let catalogCategories = [];
let catalogFilterRequestId = 0;
let catalogSearchTimeout = null;
const catalogSearchDelayMs = 300;
const catalogPageSize = 6;

let catalogPagination = {
    page: 1,
    page_size: catalogPageSize,
    total: 0,
    total_pages: 0,
    has_next: false,
    has_previous: false,
};

function getProductCategory(product) {
    return product?.category || null;
}

function getProductCategoryName(product) {
    return getProductCategory(product)?.name || "";
}

function getCatalogControlValues() {
    const searchInput = document.getElementById("product-search");
    const categoryFilter = document.getElementById("product-category-filter");
    const stockFilter = document.getElementById("product-stock-filter");
    const sortSelect = document.getElementById("product-sort");

    return {
        q: (searchInput?.value || "").trim(),
        category: categoryFilter?.value || "all",
        stock: stockFilter?.value || "all",
        ordering: sortSelect?.value || "default",
    };
}

function getCatalogProductQuery(values) {
    const query = {};

    if (values.q) query.q = values.q;
    if (values.category !== "all") query.category = values.category;
    if (values.stock !== "all") query.stock = values.stock;
    if (values.ordering !== "default") query.ordering = values.ordering;

    return query;
}

function hasActiveCatalogFilters(values) {
    return Boolean(
        values.q ||
        values.category !== "all" ||
        values.stock !== "all" ||
        values.ordering !== "default"
    );
}

/*
 * Nombre: fetchCategories
 * Descripcion: Obtiene las categorias activas del catalogo desde el backend.
 */
async function fetchCategories() {
    try {
        const res = await fetch(api.categories);

        if (!res.ok) throw new Error("No se pudieron cargar las categorias");

        return await res.json();
    } catch (err) {
        console.error("fetchCategories:", err);

        return [];
    }
}

/*
 * Nombre: fetchProducts
 * Descripcion: Obtiene productos desde el backend y envia filtros por query params cuando aplica.
 */
async function fetchProducts(query = {}) {
    try {
        const params = new URLSearchParams();

        Object.entries(query).forEach(([key, value]) => {
            const cleanValue = String(value || "").trim();

            if (cleanValue) params.set(key, cleanValue);
        });

        const endpoint = params.toString()
            ? `${api.products}?${params.toString()}`
            : api.products;

        const res = await fetch(endpoint);

        if (!res.ok) throw new Error("No se pudieron cargar los productos");

        return await res.json();
    } catch (err) {
        console.error("fetchProducts:", err);

        return [];
    }
}

function normalizeProductResponse(data) {
    if (Array.isArray(data)) {
        return {
            products: data,
            pagination: {
                page: 1,
                page_size: data.length,
                total: data.length,
                total_pages: data.length ? 1 : 0,
                has_next: false,
                has_previous: false,
            },
        };
    }

    const products = Array.isArray(data?.results) ? data.results : [];
    const pagination = data?.pagination || {};

    return {
        products,
        pagination: {
            page: Number(pagination.page || 1),
            page_size: Number(pagination.page_size || catalogPageSize),
            total: Number(pagination.total || products.length),
            total_pages: Number(pagination.total_pages || 0),
            has_next: Boolean(pagination.has_next),
            has_previous: Boolean(pagination.has_previous),
        },
    };
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
 * Nombre: renderProductDetail
 * Descripcion: Renderiza la informacion ampliada de un producto dentro del modal de detalle.
 */
function renderProductDetail(product) {
    const body = document.getElementById("product-detail-body");

    if (!body || !product) return;

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
        ? `<button class="btn product-detail-add" data-id="${product.id}">Agregar al carrito</button>`
        : `<button class="btn product-detail-add" disabled>Sin stock</button>`;
    const favoriteAction = `
        <button
            class="btn btn-outline product-detail-favorite ${product.is_favorite ? "active" : ""}"
            type="button"
            data-favorite-id="${product.id}"
            aria-label="${getFavoriteButtonLabel(product)}"
            title="${getFavoriteButtonLabel(product)}"
        >
            <span class="favorite-icon" aria-hidden="true">${getFavoriteIcon(product)}</span>
            <span class="favorite-text">${product.is_favorite ? "Favorito" : "Guardar"}</span>
        </button>
    `;
    const categoryName = getProductCategoryName(product);
    const categoryBadge = categoryName
        ? `<span class="product-category-badge">${escapeHtml(categoryName)}</span>`
        : "";

    body.innerHTML = `
        <div class="product-detail-grid">
            <div class="product-detail-image">
                <img
                    src="${escapeHtml(product.image) || "/static/store/img/STLTH.webp"}"
                    alt="${escapeHtml(product.name)}"
                />
            </div>

            <div class="product-detail-info">
                <span class="product-detail-tag">Detalle del producto</span>

                <h2>${escapeHtml(product.name)}</h2>

                ${categoryBadge}

                ${renderProductRating(product)}

                <p class="muted product-detail-description">
                    ${escapeHtml(product.description || "Sin descripcion disponible.")}
                </p>

                ${stockLabel}

                <div class="product-detail-price">
                    $${Number(product.price || 0).toFixed(2)}
                </div>

                <div class="product-detail-actions">
                    ${addButton}

                    ${favoriteAction}

                    <button class="btn btn-outline product-detail-close-secondary">
                        Seguir viendo
                    </button>
                </div>
            </div>
        </div>

        <section id="product-reviews-panel" class="product-reviews-panel">
            <p class="muted">Cargando reseñas...</p>
        </section>
    `;

    document
        .querySelector(".product-detail-add")
        ?.addEventListener("click", async () => {
            await addToCart(Number(product.id), 1);
        });

    document
        .querySelector(".product-detail-favorite")
        ?.addEventListener("click", async (event) => {
            await handleFavoriteToggle(event.currentTarget, product.id);
        });

    document
        .querySelector(".product-detail-close-secondary")
        ?.addEventListener("click", () => {
            const modal = document.getElementById("product-detail-modal");
            const focusTarget = document.querySelector(`.product-card[data-id="${product.id}"]`);

            closeModalSafely(modal, focusTarget);
        });
}

/*
 * Nombre: openProductDetail
 * Descripcion: Abre el modal de detalle con la informacion del producto seleccionado.
 */
function openProductDetail(productId) {
    const modal = document.getElementById("product-detail-modal");
    const product = catalogProducts.find((item) => Number(item.id) === Number(productId));

    if (!modal || !product) return;

    renderProductDetail(product);
    loadProductReviews(product.id);

    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("open");
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

                await refreshProductsUI();
            });

        document
            .querySelector(".clear-catalog-filters")
            ?.addEventListener("click", async () => {
                resetCatalogControls();
                await applyCatalogFiltersNow();
            });

        return;
    }

    container.innerHTML = products
        .map((product) => {
            const stock = Number(product.stock || 0);
            const categoryName = getProductCategoryName(product);
            const categoryBadge = categoryName
                ? `<span class="product-category-badge">${escapeHtml(categoryName)}</span>`
                : "";

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
                <article class="product-card product-card-clickable" data-id="${product.id}" tabindex="0">
                    <img
                        src="${escapeHtml(product.image) || "/static/store/img/STLTH.webp"}"
                        alt="${escapeHtml(product.name)}"
                    />

                    ${renderFavoriteIconButton(product)}

                    <div class="product-info">
                        ${categoryBadge}

                        <h3>${escapeHtml(product.name)}</h3>

                        ${renderProductRating(product)}

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

    document.querySelectorAll(".product-card-clickable").forEach((card) => {
        card.addEventListener("click", (event) => {
            if (event.target.closest(".add-to-cart, .favorite-toggle")) return;

            openProductDetail(Number(card.dataset.id));
        });

        card.addEventListener("keydown", (event) => {
            if (event.key !== "Enter") return;
            if (event.target.closest(".favorite-toggle")) return;

            openProductDetail(Number(card.dataset.id));
        });
    });

    document.querySelectorAll(".add-to-cart").forEach((btn) => {
        btn.addEventListener("click", (event) => {
            event.stopPropagation();

            addToCart(Number(btn.dataset.id), 1);
        });
    });

    document.querySelectorAll(".favorite-toggle").forEach((btn) => {
        btn.addEventListener("click", async (event) => {
            event.stopPropagation();

            await handleFavoriteToggle(btn, btn.dataset.favoriteId);
        });
    });
}

function updateCatalogResultsInfo(currentCount, totalCount, pagination = null) {
    const resultsInfo = document.getElementById("catalog-results-info");

    if (!resultsInfo) return;

    if (!currentCount && !totalCount) {
        resultsInfo.textContent = "No hay productos cargados.";
        return;
    }

    if (pagination && totalCount) {
        const page = Number(pagination.page || 1);
        const pageSize = Number(pagination.page_size || currentCount);
        const start = ((page - 1) * pageSize) + 1;
        const end = start + currentCount - 1;

        resultsInfo.textContent = `Mostrando ${start}-${end} de ${totalCount} producto(s).`;
        return;
    }

    resultsInfo.textContent = `Mostrando ${currentCount} producto(s).`;
}

function resetCatalogControls() {
    const searchInput = document.getElementById("product-search");
    const categoryFilter = document.getElementById("product-category-filter");
    const stockFilter = document.getElementById("product-stock-filter");
    const sortSelect = document.getElementById("product-sort");

    if (searchInput) searchInput.value = "";
    if (categoryFilter) categoryFilter.value = "all";
    if (stockFilter) stockFilter.value = "all";
    if (sortSelect) sortSelect.value = "default";

    setActiveQuickFilter("all");
}

function setActiveQuickFilter(filterValue) {
    document.querySelectorAll(".quick-filter").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.filter === filterValue);
    });
}

function resetCatalogPage() {
    catalogPagination.page = 1;
}

function scheduleCatalogFilters() {
    clearTimeout(catalogSearchTimeout);
    resetCatalogPage();

    catalogSearchTimeout = setTimeout(() => {
        applyCatalogFilters();
    }, catalogSearchDelayMs);
}

async function applyCatalogFiltersNow() {
    clearTimeout(catalogSearchTimeout);
    resetCatalogPage();
    await applyCatalogFilters();
}

async function goToCatalogPage(page) {
    catalogPagination.page = Math.max(1, Number(page || 1));
    await applyCatalogFilters();
}

function renderCatalogPagination(pagination) {
    const paginationEl = document.getElementById("catalog-pagination");

    if (!paginationEl) return;

    const totalPages = Number(pagination.total_pages || 0);
    const currentPage = Number(pagination.page || 1);

    if (totalPages <= 1) {
        paginationEl.innerHTML = "";
        paginationEl.setAttribute("hidden", "hidden");
        return;
    }

    paginationEl.removeAttribute("hidden");
    paginationEl.innerHTML = `
        <button
            class="catalog-page-btn"
            type="button"
            data-page="${currentPage - 1}"
            ${pagination.has_previous ? "" : "disabled"}
        >
            Anterior
        </button>

        <span class="catalog-page-status">
            Pagina ${currentPage} de ${totalPages}
        </span>

        <button
            class="catalog-page-btn"
            type="button"
            data-page="${currentPage + 1}"
            ${pagination.has_next ? "" : "disabled"}
        >
            Siguiente
        </button>
    `;

    paginationEl.querySelectorAll(".catalog-page-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await goToCatalogPage(btn.dataset.page);
        });
    });
}

async function applyCatalogFilters() {
    const values = getCatalogControlValues();
    const query = getCatalogProductQuery(values);
    const isFiltered = hasActiveCatalogFilters(values);
    const requestId = catalogFilterRequestId + 1;
    const page = Number(catalogPagination.page || 1);

    catalogFilterRequestId = requestId;
    renderProductsSkeleton();

    const data = await fetchProducts({
        ...query,
        page,
        page_size: catalogPageSize,
    });
    const { products, pagination } = normalizeProductResponse(data);

    if (requestId !== catalogFilterRequestId) return;

    if (pagination.total_pages > 0 && page > pagination.total_pages) {
        await goToCatalogPage(pagination.total_pages);
        return;
    }

    catalogProducts = products;
    catalogPagination = pagination;

    updateCatalogResultsInfo(
        catalogProducts.length,
        catalogPagination.total,
        catalogPagination
    );
    renderCatalogPagination(catalogPagination);

    renderProducts(catalogProducts, {
        isFiltered,
    });
}

function getCategoryOptionsFromProducts(products) {
    const options = new Map();

    products.forEach((product) => {
        const category = getProductCategory(product);

        if (!category?.slug || !category?.name) return;

        options.set(category.slug, {
            slug: category.slug,
            name: category.name,
        });
    });

    return Array.from(options.values()).sort((a, b) =>
        a.name.localeCompare(b.name)
    );
}

function populateCategoryFilter(categories, products) {
    const categoryFilter = document.getElementById("product-category-filter");

    if (!categoryFilter) return;

    const currentValue = categoryFilter.value || "all";
    const options = categories.length
        ? categories
        : getCategoryOptionsFromProducts(products);

    categoryFilter.innerHTML = `
        <option value="all">Todas</option>
        ${options
            .map((category) => `
                <option value="${escapeHtml(category.slug)}">
                    ${escapeHtml(category.name)}
                </option>
            `)
            .join("")}
    `;

    const hasCurrentValue = Array.from(categoryFilter.options).some(
        (option) => option.value === currentValue
    );

    categoryFilter.value = hasCurrentValue ? currentValue : "all";
}

/*
 * Nombre: initCatalogControls
 * Descripcion: Conecta los controles del catalogo con los filtros del backend.
 */
function initCatalogControls() {
    const searchInput = document.getElementById("product-search");
    const categoryFilter = document.getElementById("product-category-filter");
    const stockFilter = document.getElementById("product-stock-filter");
    const sortSelect = document.getElementById("product-sort");

    searchInput?.addEventListener("input", () => {
        scheduleCatalogFilters();
    });

    categoryFilter?.addEventListener("change", () => {
        applyCatalogFiltersNow();
    });

    stockFilter?.addEventListener("change", () => {
        setActiveQuickFilter(stockFilter.value);
        applyCatalogFiltersNow();
    });

    sortSelect?.addEventListener("change", () => {
        applyCatalogFiltersNow();
    });

    document.querySelectorAll(".quick-filter").forEach((btn) => {
        btn.addEventListener("click", () => {
            const filterValue = btn.dataset.filter || "all";

            if (stockFilter) {
                stockFilter.value = filterValue;
            }

            setActiveQuickFilter(filterValue);
            applyCatalogFiltersNow();
        });
    });
}

async function refreshProductsUI() {
    catalogCategories = await fetchCategories();

    populateCategoryFilter(catalogCategories, catalogProducts);

    await applyCatalogFilters();
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

async function updateCartItemQuantity(productId, quantity) {
    const res = await fetch(api.cartUpdate, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify({ productId, quantity }),
    });

    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudo actualizar la cantidad");
    }

    await updateCartUI();

    return data;
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
 * Nombre: clearCart
 * Descripcion: Vacia completamente el carrito usando el endpoint del backend y actualiza la interfaz.
 */
async function clearCart() {
    if (!api.cartClear) {
        console.error("No existe api.cartClear en el objeto api.");
        showCartFeedback("No se pudo vaciar el carrito. Falta configurar la ruta.", "error");
        return;
    }

    try {
        const res = await fetch(api.cartClear, {
            method: "POST",
            headers: csrfHeaders(),
            credentials: "include",
        });

        if (!res.ok) {
            console.error("clearCart fallo:", res.status, await res.text());
            showCartFeedback("No se pudo vaciar el carrito.", "error");
            return;
        }

        localStorage.removeItem("cart");

        clearShippingForm();
        resetCheckoutSummary();

        await updateCartUI();

        showCartFeedback("Carrito vaciado correctamente.", "success");
        showToast("Carrito vaciado correctamente.", "success");
    } catch (err) {
        console.warn("clearCart error de red:", err);
        showCartFeedback("Error de red al vaciar el carrito.", "error");
    }
}

function setCouponStatus(message = "", type = "") {
    const status = document.getElementById("coupon-status");

    if (!status) return;

    status.textContent = message;
    status.className = `coupon-status ${type}`.trim();
}

function renderCouponState(cartData = {}) {
    const input = document.getElementById("coupon-code");
    const removeBtn = document.getElementById("coupon-remove-btn");
    const coupon = cartData?.coupon || null;
    const discount = Number(cartData?.discount || 0);

    if (!input || !removeBtn) return;

    if (coupon) {
        input.value = coupon.code || "";
        removeBtn.hidden = false;
        setCouponStatus(
            `Cupon ${coupon.code} aplicado. Descuento: $${discount.toFixed(2)}.`,
            "success"
        );

        return;
    }

    removeBtn.hidden = true;

    if (cartData?.coupon_error) {
        setCouponStatus(cartData.coupon_error, "error");
        return;
    }

    setCouponStatus("", "");
}

async function applyCoupon(code) {
    const res = await fetch(api.cartApplyCoupon, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
        body: JSON.stringify({ code }),
    });
    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudo aplicar el cupon.");
    }

    return data;
}

async function removeCoupon() {
    const res = await fetch(api.cartRemoveCoupon, {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
    });
    const data = await res.json();

    if (!res.ok) {
        throw new Error(data?.error || "No se pudo quitar el cupon.");
    }

    return data;
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
    let cartData = null;

    const serverCart = await getServerCart();

    if (serverCart && Array.isArray(serverCart.items)) {
        items = serverCart.items;
        cartData = serverCart;
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
                    image: "/static/store/img/STLTH.webp",
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

        renderCouponState(serverCart || {
            subtotal: 0,
            discount: 0,
            total: 0,
            coupon: null,
        });
        resetCheckoutSummary();

        return;
    }

    itemsEl.innerHTML = items
        .map((item) => {
            const price = Number(item.product.price || 0);
            const quantity = Number(item.quantity || 0);
            const stock = Number(item.product.stock || 0);
            const subtotal = price * quantity;
            const isMaxStock = quantity >= stock;

            const stockMessage = isMaxStock && stock > 0
                ? `<p class="cart-stock-limit">Stock máximo alcanzado</p>`
                : "";

            return `
                <div class="cart-item" data-id="${item.product.id}">
                    <img
                        src="${escapeHtml(item.product.image || "/static/store/img/STLTH.webp")}"
                        alt="${escapeHtml(item.product.name)}"
                    />

                    <div class="cart-item-info">
                        <strong>${escapeHtml(item.product.name)}</strong>

                        <small>
                            $${price.toFixed(2)} x ${quantity}
                        </small>

                        <span class="cart-line-subtotal">
                            Subtotal: $${subtotal.toFixed(2)}
                        </span>

                        ${stockMessage}
                    </div>

                    <div class="cart-item-actions">
                        <button class="btn small decrease-item" data-id="${item.product.id}">
                            -
                        </button>

                        <input
                            class="cart-qty-input"
                            type="number"
                            min="1"
                            max="${stock}"
                            value="${quantity}"
                            data-id="${item.product.id}"
                            data-current="${quantity}"
                            aria-label="Cantidad de ${escapeHtml(item.product.name)}"
                        />

                        <button
                            class="btn small increase-item"
                            data-id="${item.product.id}"
                            ${isMaxStock ? "disabled" : ""}
                            title="${isMaxStock ? "Stock máximo alcanzado" : "Agregar una unidad"}"
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
        btn.addEventListener("click", async () => {
            await removeFromCart(Number(btn.dataset.id));
        });
    });

    document.querySelectorAll(".increase-item").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await addToCart(Number(btn.dataset.id), 1);
        });
    });

    document.querySelectorAll(".decrease-item").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await decreaseCartItem(Number(btn.dataset.id));
        });
    });

    document.querySelectorAll(".cart-qty-input").forEach((input) => {
        input.addEventListener("change", async () => {
            const productId = Number(input.dataset.id);
            const previousValue = Number(input.dataset.current || 1);
            const stock = Number(input.max || 0);
            const quantity = Number(input.value);

            if (!Number.isInteger(quantity) || quantity < 1) {
                input.value = String(previousValue);
                showCartFeedback("Ingresa una cantidad valida.", "error");
                return;
            }

            if (stock > 0 && quantity > stock) {
                input.value = String(previousValue);
                showCartFeedback("La cantidad supera el stock disponible.", "error");
                return;
            }

            try {
                input.disabled = true;
                await updateCartItemQuantity(productId, quantity);
                clearCartFeedback();
            } catch (err) {
                input.value = String(previousValue);
                showCartFeedback(
                    err.message || "No se pudo actualizar la cantidad.",
                    "error"
                );
                await updateCartUI();
            } finally {
                input.disabled = false;
            }
        });

        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                input.blur();
            }
        });
    });

    const calculatedTotal = items.reduce(
        (sum, item) => sum + Number(item.product.price) * Number(item.quantity),
        0
    );
    const finalTotal = cartData ? Number(cartData.total || 0) : calculatedTotal;

    const count = items.reduce(
        (sum, item) => sum + Number(item.quantity),
        0
    );

    countEl.textContent = String(count);
    totalEl.textContent = `$${finalTotal.toFixed(2)}`;
    renderCouponState(cartData || {
        subtotal: calculatedTotal,
        discount: 0,
        total: calculatedTotal,
        coupon: null,
    });
}

// =============================================================================
//  FORMULARIO DE ENVIO Y RESUMEN DE CHECKOUT
// =============================================================================

/*
 * Nombre: getShippingFormData
 * Descripcion: Obtiene y valida los datos de envio escritos por el usuario en el carrito.
 */
function getShippingFormData() {
    const shippingName = document.getElementById("shipping-name")?.value.trim() || "";
    const shippingPhone = document.getElementById("shipping-phone")?.value.trim() || "";
    const shippingAddress = document.getElementById("shipping-address")?.value.trim() || "";
    const shippingCity = document.getElementById("shipping-city")?.value.trim() || "";
    const shippingNotes = document.getElementById("shipping-notes")?.value.trim() || "";
    const shippingAddressId = getSelectedShippingAddressId();
    const shippingData = {
        shippingName,
        shippingPhone,
        shippingAddress,
        shippingCity,
        shippingNotes,
        shippingAddressId,
    };
    const validationError = getShippingValidationError(shippingData);

    if (validationError) {
        showCartFeedback(validationError, "error");
        showToast(validationError, "error");

        return null;
    }

    return shippingData;
}

function getSavedShippingAddresses() {
    if (!Array.isArray(currentUser?.shipping_addresses)) return [];

    return currentUser.shipping_addresses;
}

function getSelectedShippingAddressId() {
    const select = document.getElementById("shipping-address-select");
    const value = select?.value || "";

    if (!value) return "";

    return value;
}

function getSelectedShippingAddress() {
    const selectedId = Number(getSelectedShippingAddressId());

    if (!selectedId) return null;

    return getSavedShippingAddresses().find(
        (address) => Number(address.id) === selectedId
    ) || null;
}

function formatShippingAddressOption(address) {
    const label = address.label || address.address || "Direccion guardada";
    const city = address.city ? ` - ${address.city}` : "";
    const suffix = address.is_default ? " (predeterminada)" : "";

    return `${label}${city}${suffix}`;
}

function setShippingAddressStatus(message = "", type = "") {
    const statusEl = document.getElementById("shipping-address-status");

    if (!statusEl) return;

    statusEl.textContent = message;
    statusEl.className = `shipping-address-status ${type}`.trim();
}

function renderShippingAddressBook(preferredAddressId = null, forcePreferred = false) {
    const book = document.getElementById("shipping-address-book");
    const select = document.getElementById("shipping-address-select");
    const deleteBtn = document.getElementById("shipping-address-delete-btn");
    const defaultBtn = document.getElementById("shipping-address-default-btn");

    if (!book || !select) return;

    if (!currentUser) {
        book.style.display = "none";
        select.innerHTML = '<option value="">Ingresar manualmente</option>';

        return;
    }

    const addresses = getSavedShippingAddresses();
    const selectedBeforeRender = select.value;
    const defaultAddressId = currentUser?.default_shipping?.id || "";
    const selectedAddressId = forcePreferred
        ? preferredAddressId || selectedBeforeRender || defaultAddressId || ""
        : selectedBeforeRender || preferredAddressId || defaultAddressId || "";

    book.style.display = "grid";
    select.innerHTML = `
        <option value="">Ingresar manualmente</option>
        ${addresses
        .map((address) => `
                <option value="${address.id}">
                    ${escapeHtml(formatShippingAddressOption(address))}
                </option>
            `)
        .join("")}
    `;

    if (
        selectedAddressId &&
        addresses.some((address) => Number(address.id) === Number(selectedAddressId))
    ) {
        select.value = String(selectedAddressId);
    }

    const hasSelectedAddress = Boolean(select.value);

    if (deleteBtn) deleteBtn.disabled = !hasSelectedAddress;
    if (defaultBtn) defaultBtn.disabled = !hasSelectedAddress;
}

function fillShippingFormFromAddress(address, onlyIfEmpty = false) {
    if (!address) return;

    const setter = onlyIfEmpty ? setInputValueIfEmpty : setInputValue;

    setter("shipping-label", address.label);
    setter("shipping-name", address.name);
    setter("shipping-phone", address.phone);
    setter("shipping-address", address.address);
    setter("shipping-city", address.city);
    setter("shipping-notes", address.notes);
}

function getShippingAddressFormPayload(isDefault = false) {
    const shippingData = getShippingFormData();

    if (!shippingData) return null;

    return {
        label: document.getElementById("shipping-label")?.value.trim() || "",
        name: shippingData.shippingName,
        phone: shippingData.shippingPhone,
        address: shippingData.shippingAddress,
        city: shippingData.shippingCity,
        notes: shippingData.shippingNotes,
        is_default: isDefault,
    };
}

function setInputValue(id, value) {
    const input = document.getElementById(id);

    if (!input) return;

    input.value = String(value || "").trim();
}

function setInputValueIfEmpty(id, value) {
    const input = document.getElementById(id);
    const cleanValue = String(value || "").trim();

    if (!input || input.value.trim() || !cleanValue) return;

    input.value = cleanValue;
}

function autofillShippingFormFromProfile() {
    const shipping = currentUser?.default_shipping || {};
    const selectedAddress = getSelectedShippingAddress();

    renderShippingAddressBook(shipping.id);

    if (selectedAddress) {
        fillShippingFormFromAddress(selectedAddress, true);
        return;
    }

    setInputValueIfEmpty("shipping-label", shipping.label);
    setInputValueIfEmpty("shipping-name", shipping.name);
    setInputValueIfEmpty("shipping-phone", shipping.phone);
    setInputValueIfEmpty("shipping-address", shipping.address);
    setInputValueIfEmpty("shipping-city", shipping.city);
    setInputValueIfEmpty("shipping-notes", shipping.notes);
}

function fillProfileForm() {
    const customer = currentUser?.customer || {};
    const firstName = document.getElementById("profile-first-name");
    const lastName = document.getElementById("profile-last-name");
    const phone = document.getElementById("profile-phone");

    if (firstName) firstName.value = customer.first_name || "";
    if (lastName) lastName.value = customer.last_name || "";
    if (phone) phone.value = customer.phone || "";
}

/*
 * Nombre: clearShippingForm
 * Descripcion: Limpia los campos del formulario de datos de envio del carrito.
 */
function clearShippingForm() {
    const shippingLabel = document.getElementById("shipping-label");
    const shippingName = document.getElementById("shipping-name");
    const shippingPhone = document.getElementById("shipping-phone");
    const shippingAddress = document.getElementById("shipping-address");
    const shippingCity = document.getElementById("shipping-city");
    const shippingNotes = document.getElementById("shipping-notes");
    const shippingAddressSelect = document.getElementById("shipping-address-select");

    if (shippingLabel) shippingLabel.value = "";
    if (shippingName) shippingName.value = "";
    if (shippingPhone) shippingPhone.value = "";
    if (shippingAddress) shippingAddress.value = "";
    if (shippingCity) shippingCity.value = "";
    if (shippingNotes) shippingNotes.value = "";
    if (shippingAddressSelect) shippingAddressSelect.value = "";

    setShippingAddressStatus();
}

/*
 * Nombre: resetCheckoutSummary
 * Descripcion: Limpia el resumen visual del paso de confirmacion del checkout.
 */
function resetCheckoutSummary() {
    const summary = document.getElementById("checkout-confirm-summary");

    if (!summary) return;

    summary.innerHTML = `
        <p class="muted">
            El resumen se generará automáticamente.
        </p>
    `;
}

// =============================================================================
//  INICIALIZACION Y EVENTOS DE INTERFAZ
// =============================================================================

function initializeCarousel() {
    const slides = document.querySelectorAll(".carousel-slide");
    const prevBtn = document.querySelector(".prev");
    const nextBtn = document.querySelector(".next");
    let index = 0;

    if (!slides.length) return;

    const showSlide = (newIndex) => {
        slides.forEach((slide) => slide.classList.remove("active"));
        slides[newIndex].classList.add("active");
    };

    prevBtn?.addEventListener("click", () => {
        index = index > 0 ? index - 1 : slides.length - 1;
        showSlide(index);
    });

    nextBtn?.addEventListener("click", () => {
        index = index < slides.length - 1 ? index + 1 : 0;
        showSlide(index);
    });

    setInterval(() => {
        index = index < slides.length - 1 ? index + 1 : 0;
        showSlide(index);
    }, 5000);

    showSlide(index);
}

function initializeThemeToggle() {
    const themeToggle = document.getElementById("theme-toggle");
    const themeIcon = themeToggle?.querySelector(".theme-icon");

    themeToggle?.addEventListener("click", () => {
        document.body.classList.toggle("light-mode");
        document.body.classList.toggle("dark-mode");

        if (themeIcon) {
            themeIcon.textContent = document.body.classList.contains("light-mode")
                ? "☀"
                : "☾";
        }
    });
}

/*
 * Nombre: Modulo de inicializacion y eventos de interfaz
 * Descripcion: Conecta los elementos del DOM con las funciones principales cuando la pagina termina de cargar.
 */
document.addEventListener("DOMContentLoaded", async () => {
    initializeCarousel();
    initializeThemeToggle();

    const ageConfirmBtn = document.getElementById("age-confirm-btn");
    const ageDenyBtn = document.getElementById("age-deny-btn");

    ageConfirmBtn?.addEventListener("click", confirmAgeVerification);
    ageDenyBtn?.addEventListener("click", denyAgeVerification);

    if (!hasAgeVerification()) {
        showAgeVerification();
    }

    await refreshAuthState();

    renderProductsSkeleton();

    initCatalogControls();
    await refreshProductsUI();

    await updateCartUI();

    const cartToggle = document.getElementById("cart-toggle");
    const cartDrawer = document.getElementById("cart-drawer");
    const cartClose = document.getElementById("cart-close");

    const continueShoppingBtn = document.getElementById("continue-shopping-btn");
    const clearCartBtn = document.getElementById("clear-cart-btn");
    const couponForm = document.getElementById("coupon-form");
    const couponInput = document.getElementById("coupon-code");
    const couponApplyBtn = document.getElementById("coupon-apply-btn");
    const couponRemoveBtn = document.getElementById("coupon-remove-btn");
    const checkoutBtn = document.getElementById("checkout-btn");
    const checkoutPrevBtn = document.getElementById("checkout-prev-btn");
    const checkoutNextBtn = document.getElementById("checkout-next-btn");
    const checkoutStepIndicators = document.querySelectorAll(".checkout-step-indicator");
    const shippingAddressSelect = document.getElementById("shipping-address-select");
    const shippingAddressSaveBtn = document.getElementById("shipping-address-save-btn");
    const shippingAddressDefaultBtn = document.getElementById("shipping-address-default-btn");
    const shippingAddressDeleteBtn = document.getElementById("shipping-address-delete-btn");

    const productDetailModal = document.getElementById("product-detail-modal");
    const productDetailClose = document.getElementById("product-detail-close");

    const authModal = document.getElementById("auth-modal");
    const btnOpenAuth = document.getElementById("open-auth");
    const btnLogout = document.getElementById("logout-btn");
    const authClose = document.getElementById("auth-close");
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    const passwordResetRequestForm = document.getElementById("password-reset-request-form");
    const passwordResetConfirmForm = document.getElementById("password-reset-confirm-form");
    const profileBtn = document.getElementById("profile-btn");
    const profileModal = document.getElementById("profile-modal");
    const profileClose = document.getElementById("profile-close");
    const profileForm = document.getElementById("profile-form");
    const profilePasswordForm = document.getElementById("profile-password-form");
    const contactForm = document.getElementById("contact-form");
    const contactName = document.getElementById("contact-name");
    const contactEmail = document.getElementById("contact-email");
    const contactPhone = document.getElementById("contact-phone");
    const contactMessage = document.getElementById("contact-message");

    const myOrdersBtn = document.getElementById("my-orders-btn");
    const ordersModal = document.getElementById("orders-modal");
    const ordersClose = document.getElementById("orders-close");
    const ordersStatusFilter = document.getElementById("orders-status-filter");
    const ordersConfirmYes = document.getElementById("orders-confirm-yes");
    const ordersConfirmNo = document.getElementById("orders-confirm-no");
    const favoritesBtn = document.getElementById("favorites-btn");
    const favoritesModal = document.getElementById("favorites-modal");
    const favoritesClose = document.getElementById("favorites-close");

    const checkoutSuccessModal = document.getElementById("checkout-success-modal");
    const checkoutSuccessClose = document.getElementById("checkout-success-close");
    const checkoutSuccessOrders = document.getElementById("checkout-success-orders");
    const checkoutSuccessContinue = document.getElementById("checkout-success-continue");

    let currentCheckoutStep = "cart";

    function showAuthPanel(panel) {
        const panels = {
            login: loginForm,
            register: registerForm,
            resetRequest: passwordResetRequestForm,
            resetConfirm: passwordResetConfirmForm,
        };

        Object.values(panels).forEach((form) => {
            if (form) form.style.display = "none";
        });

        if (panels[panel]) {
            panels[panel].style.display = "block";
        }
    }

    function openPasswordResetConfirmFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const uid = params.get("uid") || "";
        const token = params.get("token") || "";

        if (params.get("reset_password") !== "1" || !uid || !token) {
            return;
        }

        setInputValue("password-reset-uid", uid);
        setInputValue("password-reset-token", token);
        showAuthPanel("resetConfirm");
        showAuthFeedback("Ingresa tu nueva contrasena.", "success");

        authModal?.setAttribute("aria-hidden", "false");
        authModal?.classList.add("open");

        window.history.replaceState(
            {},
            document.title,
            `${window.location.pathname}${window.location.hash}`
        );
    }

    function getActiveCheckoutStep() {
        const activeIndicator = document.querySelector(".checkout-step-indicator.active");

        return activeIndicator?.dataset.step || currentCheckoutStep || "cart";
    }

    function setCheckoutStep(step) {
        currentCheckoutStep = step;

        document.querySelectorAll(".checkout-step-panel").forEach((panel) => {
            panel.classList.remove("active");
        });

        document
            .getElementById(`checkout-step-${step}`)
            ?.classList.add("active");

        checkoutStepIndicators.forEach((indicator) => {
            indicator.classList.toggle(
                "active",
                indicator.dataset.step === step
            );
        });

        if (checkoutPrevBtn) {
            checkoutPrevBtn.style.display = step === "cart" ? "none" : "block";
        }

        if (checkoutNextBtn) {
            checkoutNextBtn.style.display = step === "confirm" ? "none" : "block";
        }

        if (checkoutBtn) {
            checkoutBtn.style.display = step === "confirm" ? "block" : "none";
        }
    }

    async function cartHasItems() {
        const serverCart = await getServerCart();
        const localCart = getLocalCart();

        const hasServerItems =
            serverCart &&
            Array.isArray(serverCart.items) &&
            serverCart.items.length > 0;

        const hasLocalItems =
            localCart &&
            Object.keys(localCart).length > 0;

        return hasServerItems || hasLocalItems;
    }

    async function renderCheckoutConfirmSummary() {
        const summary = document.getElementById("checkout-confirm-summary");

        if (!summary) return false;

        const shippingData = getShippingFormData();

        if (!shippingData) {
            return false;
        }

        const serverCart = await getServerCart();
        const items = serverCart?.items || [];
        const total = Number(serverCart?.total || 0);
        const subtotal = Number(serverCart?.subtotal ?? total);
        const discount = Number(serverCart?.discount || 0);
        const coupon = serverCart?.coupon || null;

        if (!items.length) {
            showCartFeedback("Tu carrito esta vacio.", "error");
            resetCheckoutSummary();
            setCheckoutStep("cart");

            return false;
        }

        const itemsHtml = items
            .map((item) => {
                const price = Number(item.product?.price || 0);
                const quantity = Number(item.quantity || 0);
                const subtotal = price * quantity;

                return `
                    <div class="checkout-confirm-item">
                        <span>${escapeHtml(item.product?.name || "Producto")} x ${quantity}</span>
                        <strong>$${subtotal.toFixed(2)}</strong>
                    </div>
                `;
            })
            .join("");

        summary.innerHTML = `
            <div class="checkout-confirm-section">
                <h5>Productos</h5>
                ${itemsHtml}
            </div>

            <div class="checkout-confirm-section">
                <h5>Envío</h5>

                <p>
                    <strong>Nombre:</strong>
                    ${escapeHtml(shippingData.shippingName)}
                </p>

                <p>
                    <strong>Teléfono:</strong>
                    ${escapeHtml(shippingData.shippingPhone)}
                </p>

                <p>
                    <strong>Dirección:</strong>
                    ${escapeHtml(shippingData.shippingAddress)}
                </p>

                <p>
                    <strong>Ciudad:</strong>
                    ${escapeHtml(shippingData.shippingCity)}
                </p>

                ${shippingData.shippingNotes
                ? `
                            <p>
                                <strong>Notas:</strong>
                                ${escapeHtml(shippingData.shippingNotes)}
                            </p>
                        `
                : ""
            }
            </div>

            <div class="checkout-confirm-total checkout-confirm-subtotal">
                <span>Subtotal</span>
                <strong>$${subtotal.toFixed(2)}</strong>
            </div>

            ${discount > 0
                ? `
                    <div class="checkout-confirm-total checkout-confirm-discount">
                        <span>Descuento${coupon?.code ? ` (${escapeHtml(coupon.code)})` : ""}</span>
                        <strong>-$${discount.toFixed(2)}</strong>
                    </div>
                `
                : ""
            }

            <div class="checkout-confirm-total">
                <span>Total a pagar</span>
                <strong>$${total.toFixed(2)}</strong>
            </div>
        `;

        return true;
    }

    cartToggle?.addEventListener("click", () => {
        clearCartFeedback();
        resetCheckoutSummary();
        setCheckoutStep("cart");

        cartDrawer?.setAttribute("aria-hidden", "false");
        cartDrawer?.classList.add("open");
    });

    cartClose?.addEventListener("click", () => {
        closeModalSafely(cartDrawer, cartToggle);
    });

    continueShoppingBtn?.addEventListener("click", () => {
        closeModalSafely(cartDrawer, cartToggle);

        document
            .getElementById("productos")
            ?.scrollIntoView({
                behavior: "smooth",
            });
    });

    clearCartBtn?.addEventListener("click", async () => {
        await clearCart();

        resetCheckoutSummary();
        setCheckoutStep("cart");
    });

    shippingAddressSelect?.addEventListener("change", () => {
        const selectedAddress = getSelectedShippingAddress();

        setShippingAddressStatus();

        if (selectedAddress) {
            fillShippingFormFromAddress(selectedAddress);
        } else {
            setInputValue("shipping-label", "");
        }

        renderShippingAddressBook(shippingAddressSelect.value);
    });

    shippingAddressSaveBtn?.addEventListener("click", async () => {
        if (!currentUser) {
            await refreshAuthState();
        }

        if (!currentUser) {
            setShippingAddressStatus(
                "Inicia sesion para guardar direcciones.",
                "error"
            );
            return;
        }

        const selectedAddressId = getSelectedShippingAddressId();
        const payload = getShippingAddressFormPayload(false);

        if (!payload) return;

        const originalText = shippingAddressSaveBtn.textContent;
        shippingAddressSaveBtn.disabled = true;
        shippingAddressSaveBtn.textContent = "Guardando...";

        try {
            const data = await saveShippingAddress(
                payload,
                selectedAddressId || null
            );
            const savedAddressId =
                data.saved_shipping_address_id ||
                selectedAddressId ||
                data.default_shipping?.id ||
                "";

            setAuthUI(true, data);
            renderShippingAddressBook(savedAddressId, true);
            setShippingAddressStatus("Direccion guardada.", "success");
            showToast("Direccion guardada correctamente.", "success");
        } catch (err) {
            setShippingAddressStatus(
                err.message || "No se pudo guardar la direccion.",
                "error"
            );
            showToast(err.message || "No se pudo guardar la direccion.", "error");
        } finally {
            shippingAddressSaveBtn.disabled = false;
            shippingAddressSaveBtn.textContent = originalText;
        }
    });

    shippingAddressDefaultBtn?.addEventListener("click", async () => {
        const selectedAddressId = getSelectedShippingAddressId();

        if (!selectedAddressId) {
            setShippingAddressStatus("Selecciona una direccion guardada.", "error");
            return;
        }

        const originalText = shippingAddressDefaultBtn.textContent;
        shippingAddressDefaultBtn.disabled = true;
        shippingAddressDefaultBtn.textContent = "Guardando...";

        try {
            const data = await saveShippingAddress(
                { is_default: true },
                selectedAddressId
            );

            setAuthUI(true, data);
            renderShippingAddressBook(selectedAddressId, true);
            setShippingAddressStatus("Direccion predeterminada actualizada.", "success");
            showToast("Direccion predeterminada actualizada.", "success");
        } catch (err) {
            setShippingAddressStatus(
                err.message || "No se pudo actualizar la direccion.",
                "error"
            );
            showToast(err.message || "No se pudo actualizar la direccion.", "error");
        } finally {
            shippingAddressDefaultBtn.disabled = false;
            shippingAddressDefaultBtn.textContent = originalText;
        }
    });

    shippingAddressDeleteBtn?.addEventListener("click", async () => {
        const selectedAddressId = getSelectedShippingAddressId();

        if (!selectedAddressId) {
            setShippingAddressStatus("Selecciona una direccion guardada.", "error");
            return;
        }

        const originalText = shippingAddressDeleteBtn.textContent;
        shippingAddressDeleteBtn.disabled = true;
        shippingAddressDeleteBtn.textContent = "Eliminando...";

        try {
            const data = await deleteShippingAddress(selectedAddressId);

            setAuthUI(true, data);
            renderShippingAddressBook(data.default_shipping?.id || null, true);
            setShippingAddressStatus("Direccion eliminada.", "success");
            showToast("Direccion eliminada correctamente.", "success");
        } catch (err) {
            setShippingAddressStatus(
                err.message || "No se pudo eliminar la direccion.",
                "error"
            );
            showToast(err.message || "No se pudo eliminar la direccion.", "error");
        } finally {
            shippingAddressDeleteBtn.disabled = false;
            shippingAddressDeleteBtn.textContent = originalText;
        }
    });

    couponForm?.addEventListener("submit", async (event) => {
        event.preventDefault();

        const code = couponInput?.value.trim() || "";

        if (!code) {
            setCouponStatus("Ingresa un codigo de cupon.", "error");
            return;
        }

        if (couponApplyBtn) {
            couponApplyBtn.disabled = true;
            couponApplyBtn.textContent = "Aplicando...";
        }

        try {
            const data = await applyCoupon(code);

            renderCouponState(data);
            resetCheckoutSummary();
            await updateCartUI();
            showToast(data?.message || "Cupon aplicado correctamente.", "success");
        } catch (err) {
            setCouponStatus(
                err.message || "No se pudo aplicar el cupon.",
                "error"
            );
            showToast(err.message || "No se pudo aplicar el cupon.", "error");
        } finally {
            if (couponApplyBtn) {
                couponApplyBtn.disabled = false;
                couponApplyBtn.textContent = "Aplicar";
            }
        }
    });

    couponRemoveBtn?.addEventListener("click", async () => {
        couponRemoveBtn.disabled = true;

        try {
            const data = await removeCoupon();

            if (couponInput) {
                couponInput.value = "";
            }

            renderCouponState(data);
            resetCheckoutSummary();
            await updateCartUI();
            showToast(data?.message || "Cupon removido correctamente.", "success");
        } catch (err) {
            setCouponStatus(
                err.message || "No se pudo quitar el cupon.",
                "error"
            );
            showToast(err.message || "No se pudo quitar el cupon.", "error");
        } finally {
            couponRemoveBtn.disabled = false;
        }
    });

    checkoutNextBtn?.addEventListener("click", async () => {
        const activeStep = getActiveCheckoutStep();

        if (activeStep === "cart") {
            const hasItems = await cartHasItems();

            if (!hasItems) {
                showCartFeedback("Tu carrito esta vacio.", "error");
                resetCheckoutSummary();
                setCheckoutStep("cart");

                return;
            }

            autofillShippingFormFromProfile();
            setCheckoutStep("shipping");
            return;
        }

        if (activeStep === "shipping") {
            const isSummaryReady = await renderCheckoutConfirmSummary();

            if (!isSummaryReady) {
                return;
            }

            setCheckoutStep("confirm");
        }
    });

    checkoutPrevBtn?.addEventListener("click", (event) => {
        event.preventDefault();

        const activeStep = getActiveCheckoutStep();

        if (activeStep === "confirm") {
            setCheckoutStep("shipping");
            return;
        }

        if (activeStep === "shipping") {
            setCheckoutStep("cart");
        }
    });

    checkoutStepIndicators.forEach((indicator) => {
        indicator.addEventListener("click", async () => {
            const targetStep = indicator.dataset.step;

            if (targetStep === "cart") {
                setCheckoutStep("cart");
                return;
            }

            if (targetStep === "shipping") {
                const hasItems = await cartHasItems();

                if (!hasItems) {
                    showCartFeedback("Tu carrito esta vacio.", "error");
                    resetCheckoutSummary();
                    setCheckoutStep("cart");

                    return;
                }

                autofillShippingFormFromProfile();
                setCheckoutStep("shipping");
                return;
            }

            if (targetStep === "confirm") {
                const isSummaryReady = await renderCheckoutConfirmSummary();

                if (!isSummaryReady) {
                    return;
                }

                setCheckoutStep("confirm");
            }
        });
    });

    checkoutBtn?.addEventListener("click", async () => {
        const originalText = checkoutBtn.textContent;

        if (!hasAgeVerification()) {
            showCartFeedback(
                "Confirma que eres mayor de edad para finalizar el pedido.",
                "error"
            );
            showToast("Debes confirmar la verificacion de edad.", "error");
            showAgeVerification();

            return;
        }

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
            resetCheckoutSummary();
            setCheckoutStep("cart");

            return;
        }

        const shippingData = getShippingFormData();

        if (!shippingData) {
            setCheckoutStep("shipping");
            return;
        }

        const cartFingerprint = buildCheckoutCartFingerprint(
            serverCart,
            localCart
        );
        const idempotencyKey = getCheckoutIdempotencyKey(cartFingerprint);

        checkoutBtn.disabled = true;
        checkoutBtn.textContent = "Procesando...";

        let okData = null;

        try {
            const res = await fetch(api.checkout, {
                method: "POST",
                headers: {
                    ...csrfHeaders(),
                    "Idempotency-Key": idempotencyKey,
                },
                credentials: "include",
                body: JSON.stringify({
                    ...shippingData,
                    ageConfirmed: hasAgeVerification(),
                }),
            });

            if (!res.ok) {
                let msg = "Error en el pago. Intenta nuevamente.";
                let data = null;

                try {
                    data = await res.json();

                    msg = data?.error || data?.detail || data?.message || msg;
                } catch {
                    // Se conserva el mensaje por defecto.
                }

                if (data?.cart_updated) {
                    localStorage.removeItem("cart");
                    resetCheckoutSummary();
                    setCheckoutStep("cart");

                    try {
                        await updateCartUI();
                    } catch (err) {
                        console.warn("Error actualizando carrito sincronizado:", err);
                    }

                    try {
                        await refreshProductsUI();
                    } catch (err) {
                        console.warn("Error actualizando productos sincronizados:", err);
                    }

                    showToast("Actualizamos tu carrito. Revisalo antes de pagar.", "info");
                }

                if (data?.coupon_invalid) {
                    resetCheckoutSummary();
                    setCheckoutStep("cart");

                    try {
                        await updateCartUI();
                    } catch (err) {
                        console.warn("Error actualizando carrito por cupon invalido:", err);
                    }
                }

                if (res.status === 401 || res.status === 403) {
                    msg = "Inicia sesion para pagar";
                    btnOpenAuth?.click();
                }

                showCartFeedback(msg, "error");
                return;
            }

            okData = await res.json();
            clearCheckoutIdempotencyKey();
        } catch (err) {
            console.warn("checkout error:", err);
            showCartFeedback("No se pudo conectar con el servidor.", "error");
            return;
        } finally {
            checkoutBtn.disabled = false;
            checkoutBtn.textContent = originalText;
        }

        localStorage.removeItem("cart");

        clearShippingForm();
        resetCheckoutSummary();
        setCheckoutStep("cart");

        try {
            await updateCartUI();
        } catch (err) {
            console.warn("Error actualizando carrito despues del checkout:", err);
        }

        try {
            await refreshProductsUI();
        } catch (err) {
            console.warn("Error actualizando productos despues del checkout:", err);
        }

        try {
            closeModalSafely(cartDrawer, cartToggle);
        } catch (err) {
            console.warn("Error cerrando carrito despues del checkout:", err);
        }

        showCheckoutSuccess(okData);
        showToast("Compra realizada con exito.", "success");
    });

    productDetailClose?.addEventListener("click", () => {
        closeModalSafely(productDetailModal);
    });

    btnOpenAuth?.addEventListener("click", () => {
        clearAuthFeedback();
        showAuthPanel("login");

        authModal?.setAttribute("aria-hidden", "false");
        authModal?.classList.add("open");
    });

    authClose?.addEventListener("click", () => {
        closeModalSafely(authModal, btnOpenAuth);
    });

    profileBtn?.addEventListener("click", async () => {
        clearProfileFeedback();

        if (!currentUser) {
            await refreshAuthState();
        }

        fillProfileForm();
        profilePasswordForm?.reset();
        profileModal?.setAttribute("aria-hidden", "false");
        profileModal?.classList.add("open");
    });

    profileClose?.addEventListener("click", () => {
        closeModalSafely(profileModal, profileBtn);
    });

    profileForm?.addEventListener("submit", async (event) => {
        event.preventDefault();

        clearProfileFeedback();

        const submitBtn = profileForm.querySelector("button[type='submit']");
        const originalText = submitBtn?.textContent || "Guardar cambios";

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Guardando...";
        }

        try {
            const data = await updateProfile({
                first_name: document.getElementById("profile-first-name")?.value || "",
                last_name: document.getElementById("profile-last-name")?.value || "",
                phone: document.getElementById("profile-phone")?.value || "",
            });

            currentUser = data;
            setAuthUI(true, data);
            fillProfileForm();
            showProfileFeedback("Perfil actualizado correctamente.", "success");
            showToast("Perfil actualizado correctamente.", "success");
        } catch (err) {
            showProfileFeedback(
                err.message || "No se pudo actualizar el perfil.",
                "error"
            );
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
        }
    });

    profilePasswordForm?.addEventListener("submit", async (event) => {
        event.preventDefault();

        clearProfileFeedback();

        const currentPassword =
            document.getElementById("profile-current-password")?.value || "";
        const newPassword =
            document.getElementById("profile-new-password")?.value || "";
        const newPasswordConfirm =
            document.getElementById("profile-new-password-confirm")?.value || "";
        const submitBtn = profilePasswordForm.querySelector("button[type='submit']");
        const originalText = submitBtn?.textContent || "Cambiar contrasena";

        if (isEmpty(currentPassword)) {
            showProfileFeedback("Ingresa tu contrasena actual.", "error");
            return;
        }

        if (isEmpty(newPassword)) {
            showProfileFeedback("Ingresa una nueva contrasena.", "error");
            return;
        }

        if (newPassword.length < authPasswordMinLength) {
            showProfileFeedback(
                `La contrasena debe tener al menos ${authPasswordMinLength} caracteres.`,
                "error"
            );
            return;
        }

        if (newPassword !== newPasswordConfirm) {
            showProfileFeedback("Las contrasenas nuevas no coinciden.", "error");
            return;
        }

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Guardando...";
        }

        try {
            const data = await changePassword({
                current_password: currentPassword,
                new_password: newPassword,
                new_password_confirm: newPasswordConfirm,
            });

            profilePasswordForm.reset();
            showProfileFeedback(
                data?.message || "Contrasena actualizada correctamente.",
                "success"
            );
            showToast("Contrasena actualizada correctamente.", "success");
        } catch (err) {
            showProfileFeedback(
                err.message || "No se pudo actualizar la contrasena.",
                "error"
            );
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
        }
    });

    document.getElementById("show-register")?.addEventListener("click", (e) => {
        e.preventDefault();

        clearAuthFeedback();
        showAuthPanel("register");
    });

    document.getElementById("show-login")?.addEventListener("click", (e) => {
        e.preventDefault();

        clearAuthFeedback();
        showAuthPanel("login");
    });

    document.querySelectorAll(".show-login-link").forEach((link) => {
        link.addEventListener("click", (e) => {
            e.preventDefault();

            clearAuthFeedback();
            showAuthPanel("login");
        });
    });

    document.getElementById("show-password-reset-request")?.addEventListener("click", (e) => {
        e.preventDefault();

        clearAuthFeedback();
        showAuthPanel("resetRequest");
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
            await refreshProductsUI();
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

        if (password.length < authPasswordMinLength) {
            showAuthFeedback(
                `La contrasena debe tener al menos ${authPasswordMinLength} caracteres.`,
                "error"
            );
            return;
        }

        try {
            await registerUser(name, email, password);

            showAuthFeedback("Cuenta creada correctamente.", "success");

            setTimeout(async () => {
                closeModalSafely(authModal, btnOpenAuth);

                await refreshAuthState();
                await updateCartUI();
                await refreshProductsUI();
            }, 800);
        } catch (err) {
            showAuthFeedback(err.message || "No se pudo registrar la cuenta.", "error");
        }
    });

    passwordResetRequestForm?.addEventListener("submit", async (e) => {
        e.preventDefault();

        clearAuthFeedback();

        const email = document.getElementById("password-reset-email")?.value || "";
        const submitBtn = passwordResetRequestForm.querySelector("button[type='submit']");
        const originalText = submitBtn?.textContent || "Enviar enlace";

        if (isEmpty(email) || !isValidEmail(email)) {
            showAuthFeedback("Ingresa un correo valido.", "error");
            return;
        }

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Enviando...";
        }

        try {
            const data = await requestPasswordReset(email);
            passwordResetRequestForm.reset();
            showAuthFeedback(
                data?.message ||
                "Si el correo existe, enviaremos instrucciones para restablecer la contrasena.",
                "success"
            );
        } catch (err) {
            showAuthFeedback(
                err.message || "No se pudo solicitar la recuperacion.",
                "error"
            );
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
        }
    });

    passwordResetConfirmForm?.addEventListener("submit", async (e) => {
        e.preventDefault();

        clearAuthFeedback();

        const uid = document.getElementById("password-reset-uid")?.value || "";
        const token = document.getElementById("password-reset-token")?.value || "";
        const password = document.getElementById("password-reset-new")?.value || "";
        const passwordConfirm = document.getElementById("password-reset-confirm")?.value || "";
        const submitBtn = passwordResetConfirmForm.querySelector("button[type='submit']");
        const originalText = submitBtn?.textContent || "Guardar contrasena";

        if (isEmpty(password)) {
            showAuthFeedback("Ingresa una nueva contrasena.", "error");
            return;
        }

        if (password.length < authPasswordMinLength) {
            showAuthFeedback(
                `La contrasena debe tener al menos ${authPasswordMinLength} caracteres.`,
                "error"
            );
            return;
        }

        if (password !== passwordConfirm) {
            showAuthFeedback("Las contrasenas no coinciden.", "error");
            return;
        }

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Guardando...";
        }

        try {
            await confirmPasswordReset(uid, token, password, passwordConfirm);
            passwordResetConfirmForm.reset();
            showAuthPanel("login");
            showAuthFeedback("Contrasena actualizada. Inicia sesion.", "success");
        } catch (err) {
            showAuthFeedback(
                err.message || "No se pudo actualizar la contrasena.",
                "error"
            );
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
        }
    });

    btnLogout?.addEventListener("click", async () => {
        await logoutUser();
    });

    favoritesBtn?.addEventListener("click", async () => {
        favoritesModal?.setAttribute("aria-hidden", "false");
        favoritesModal?.classList.add("open");

        await loadAndRenderFavorites();
    });

    favoritesClose?.addEventListener("click", () => {
        clearFavoritesFeedback();

        closeModalSafely(favoritesModal, favoritesBtn);
    });

    contactForm?.addEventListener("submit", async (event) => {
        event.preventDefault();

        clearContactFeedback();

        const contactData = {
            name: contactName?.value || "",
            email: contactEmail?.value || "",
            phone: contactPhone?.value || "",
            message: contactMessage?.value || "",
        };
        const contactSubmit = contactForm.querySelector('input[type="submit"]');
        const originalText = contactSubmit?.value || "Enviar";

        if (isEmpty(contactData.email)) {
            showContactFeedback("Ingresa tu correo electronico.", "error");
            return;
        }

        if (!isValidEmail(contactData.email)) {
            showContactFeedback("Ingresa un correo valido.", "error");
            return;
        }

        const whatsappWindow = window.open("about:blank", "_blank");

        if (whatsappWindow) {
            whatsappWindow.opener = null;
        }

        if (contactSubmit) {
            contactSubmit.disabled = true;
            contactSubmit.value = "Enviando...";
        }

        try {
            const data = await submitContactLead(contactData);

            contactForm.reset();

            showContactFeedback(
                data?.message || "Gracias. Registramos tu correo correctamente.",
                "success"
            );
            showToast("Contacto registrado correctamente.", "success");

            if (data?.whatsapp_url) {
                if (whatsappWindow) {
                    whatsappWindow.location.href = data.whatsapp_url;
                } else {
                    window.open(data.whatsapp_url, "_blank", "noopener,noreferrer");
                }
            }
        } catch (err) {
            if (whatsappWindow && !whatsappWindow.closed) {
                whatsappWindow.close();
            }

            showContactFeedback(
                err.message || "No se pudo registrar el contacto.",
                "error"
            );
            showToast("No se pudo enviar el contacto.", "error");
        } finally {
            if (contactSubmit) {
                contactSubmit.disabled = false;
                contactSubmit.value = originalText;
            }
        }
    });

    checkoutSuccessClose?.addEventListener("click", () => {
        closeModalSafely(checkoutSuccessModal, cartToggle);
    });

    checkoutSuccessContinue?.addEventListener("click", () => {
        closeModalSafely(checkoutSuccessModal, cartToggle);

        document
            .getElementById("productos")
            ?.scrollIntoView({
                behavior: "smooth",
            });
    });

    checkoutSuccessOrders?.addEventListener("click", () => {
        closeModalSafely(checkoutSuccessModal, myOrdersBtn);

        myOrdersBtn?.click();
    });

    myOrdersBtn?.addEventListener("click", async () => {
        ordersModal?.setAttribute("aria-hidden", "false");
        ordersModal?.classList.add("open");
        ordersPagination.page = 1;
        if (ordersStatusFilter) ordersStatusFilter.value = "all";

        clearOrdersFeedback();
        hideOrderDetailPanel();

        try {
            await loadAndRenderOrders(ordersPagination.page);
        } catch {
            const body = document.getElementById("orders-body");
            const paginationEl = document.getElementById("orders-pagination");

            if (body) {
                body.innerHTML = `<p class="muted">Error cargando pedidos.</p>`;
            }

            paginationEl?.setAttribute("hidden", "hidden");
            showOrdersFeedback("No se pudieron cargar los pedidos.", "error");
        }
    });

    ordersClose?.addEventListener("click", () => {
        hideOrderCancelConfirm();
        hideOrderDetailPanel();

        closeModalSafely(ordersModal, myOrdersBtn);
    });

    ordersStatusFilter?.addEventListener("change", async () => {
        clearOrdersFeedback();
        hideOrderDetailPanel();
        ordersPagination.page = 1;

        try {
            await loadAndRenderOrders(ordersPagination.page);
        } catch {
            const body = document.getElementById("orders-body");
            const paginationEl = document.getElementById("orders-pagination");

            if (body) {
                body.innerHTML = `<p class="muted">Error cargando pedidos.</p>`;
            }

            paginationEl?.setAttribute("hidden", "hidden");
            showOrdersFeedback("No se pudieron filtrar los pedidos.", "error");
        }
    });

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
            await loadAndRenderOrders(ordersPagination.page);

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

    setCheckoutStep("cart");
    openPasswordResetConfirmFromUrl();
});
