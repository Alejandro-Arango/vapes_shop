// App state
let cart = [];
let products = [];

// DOM Elements
const productsGrid = document.getElementById('products-grid');
const cartModal = document.getElementById('cart-modal');
const productModal = document.getElementById('product-modal');
const cartBtn = document.getElementById('cart-btn');
const cartCount = document.getElementById('cart-count');
const cartItems = document.getElementById('cart-items');
const totalPrice = document.getElementById('total-price');
const categoryFilter = document.getElementById('category-filter');
const searchBox = document.getElementById('search-box');
const checkoutBtn = document.getElementById('checkout-btn');

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    loadProducts();
    setupEventListeners();
    loadCartFromStorage();
});

// Load products from API/database
async function loadProducts() {
    try {
        // Try to fetch from PHP API
        const response = await fetch('api/products.php');
        
        if (response.ok) {
            products = await response.json();
        } else {
            throw new Error('API not available');
        }
    } catch (error) {
        console.log('Using demo data:', error.message);
        // Fallback to demo data if API is not available
        products = getDemoProducts();
    }
    
    displayProducts(products);
}

// Demo products (fallback when database is not connected)
function getDemoProducts() {
    return [
        {
            id: 1,
            name: 'Vape Pod Premium',
            description: 'Dispositivo compacto y elegante con batería de larga duración',
            price: 29.99,
            category: 'vapes',
            image: '🔋'
        },
        {
            id: 2,
            name: 'Vape Mod Avanzado',
            description: 'Mod avanzado con control de temperatura y potencia',
            price: 79.99,
            category: 'vapes',
            image: '⚡'
        },
        {
            id: 3,
            name: 'Líquido Frutas Tropicales',
            description: 'Sabor a frutas tropicales, 60ml, 3mg nicotina',
            price: 14.99,
            category: 'liquidos',
            image: '🍹'
        },
        {
            id: 4,
            name: 'Líquido Menta Fresca',
            description: 'Sabor a menta refrescante, 60ml, 6mg nicotina',
            price: 14.99,
            category: 'liquidos',
            image: '🌿'
        },
        {
            id: 5,
            name: 'Líquido Café Premium',
            description: 'Sabor a café expreso, 60ml, 0mg nicotina',
            price: 16.99,
            category: 'liquidos',
            image: '☕'
        },
        {
            id: 6,
            name: 'Coils de Repuesto',
            description: 'Pack de 5 coils compatibles, resistencia 0.5ohm',
            price: 9.99,
            category: 'accesorios',
            image: '🔧'
        },
        {
            id: 7,
            name: 'Cargador USB-C',
            description: 'Cargador rápido USB-C para dispositivos vape',
            price: 7.99,
            category: 'accesorios',
            image: '🔌'
        },
        {
            id: 8,
            name: 'Estuche Protector',
            description: 'Estuche de transporte con compartimentos',
            price: 12.99,
            category: 'accesorios',
            image: '💼'
        },
        {
            id: 9,
            name: 'Vape Desechable Mix',
            description: 'Vape desechable con múltiples sabores, 2000 puffs',
            price: 8.99,
            category: 'vapes',
            image: '🌈'
        },
        {
            id: 10,
            name: 'Kit Inicial Completo',
            description: 'Kit completo para principiantes con todo lo necesario',
            price: 49.99,
            category: 'vapes',
            image: '📦'
        }
    ];
}

// Display products in grid
function displayProducts(productsToShow) {
    productsGrid.innerHTML = '';
    
    if (productsToShow.length === 0) {
        productsGrid.innerHTML = '<p class="loading">No se encontraron productos</p>';
        return;
    }
    
    productsToShow.forEach(product => {
        const productCard = createProductCard(product);
        productsGrid.appendChild(productCard);
    });
}

// Create product card element
function createProductCard(product) {
    const card = document.createElement('div');
    card.className = 'product-card';
    card.onclick = () => showProductDetail(product);
    
    card.innerHTML = `
        <div class="product-image">${product.image || '📦'}</div>
        <div class="product-info">
            <span class="product-category">${getCategoryName(product.category)}</span>
            <h3 class="product-name">${product.name}</h3>
            <p class="product-description">${product.description}</p>
            <p class="product-price">€${product.price.toFixed(2)}</p>
            <button class="add-to-cart-btn" onclick="event.stopPropagation(); addToCart(${product.id})">
                Añadir al Carrito
            </button>
        </div>
    `;
    
    return card;
}

// Get category display name
function getCategoryName(category) {
    const categories = {
        'vapes': 'Vapes',
        'liquidos': 'Líquidos',
        'accesorios': 'Accesorios'
    };
    return categories[category] || category;
}

// Show product detail modal
function showProductDetail(product) {
    const productDetail = document.getElementById('product-detail');
    productDetail.innerHTML = `
        <div class="product-image" style="width: 100%; height: 250px; font-size: 6rem;">
            ${product.image || '📦'}
        </div>
        <h2>${product.name}</h2>
        <span class="product-category">${getCategoryName(product.category)}</span>
        <p style="margin: 1rem 0;">${product.description}</p>
        <p class="product-price">€${product.price.toFixed(2)}</p>
        <button class="btn-primary" onclick="addToCart(${product.id}); closeModal('product-modal')">
            Añadir al Carrito
        </button>
    `;
    productModal.classList.add('active');
}

// Add product to cart
function addToCart(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) return;
    
    const existingItem = cart.find(item => item.id === productId);
    
    if (existingItem) {
        existingItem.quantity++;
    } else {
        cart.push({
            ...product,
            quantity: 1
        });
    }
    
    updateCart();
    saveCartToStorage();
    
    // Show feedback
    showNotification('Producto añadido al carrito');
}

// Remove product from cart
function removeFromCart(productId) {
    cart = cart.filter(item => item.id !== productId);
    updateCart();
    saveCartToStorage();
}

// Update item quantity
function updateQuantity(productId, change) {
    const item = cart.find(item => item.id === productId);
    if (!item) return;
    
    item.quantity += change;
    
    if (item.quantity <= 0) {
        removeFromCart(productId);
    } else {
        updateCart();
        saveCartToStorage();
    }
}

// Update cart display
function updateCart() {
    // Update cart count
    const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
    cartCount.textContent = totalItems;
    
    // Update cart items display
    if (cart.length === 0) {
        cartItems.innerHTML = '<p class="empty-cart">El carrito está vacío</p>';
        totalPrice.textContent = '0.00';
        return;
    }
    
    cartItems.innerHTML = cart.map(item => `
        <div class="cart-item">
            <div class="cart-item-info">
                <div class="cart-item-name">${item.name}</div>
                <div class="cart-item-price">€${item.price.toFixed(2)} x ${item.quantity}</div>
            </div>
            <div class="cart-item-quantity">
                <button class="quantity-btn" onclick="updateQuantity(${item.id}, -1)">-</button>
                <span>${item.quantity}</span>
                <button class="quantity-btn" onclick="updateQuantity(${item.id}, 1)">+</button>
            </div>
            <button class="remove-btn" onclick="removeFromCart(${item.id})">Eliminar</button>
        </div>
    `).join('');
    
    // Update total price
    const total = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    totalPrice.textContent = total.toFixed(2);
}

// Filter products
function filterProducts() {
    const category = categoryFilter.value;
    const searchTerm = searchBox.value.toLowerCase();
    
    let filtered = products;
    
    // Filter by category
    if (category !== 'all') {
        filtered = filtered.filter(p => p.category === category);
    }
    
    // Filter by search term
    if (searchTerm) {
        filtered = filtered.filter(p => 
            p.name.toLowerCase().includes(searchTerm) ||
            p.description.toLowerCase().includes(searchTerm)
        );
    }
    
    displayProducts(filtered);
}

// Setup event listeners
function setupEventListeners() {
    // Cart button
    cartBtn.addEventListener('click', () => {
        cartModal.classList.add('active');
    });
    
    // Close modals
    document.querySelectorAll('.close').forEach(closeBtn => {
        closeBtn.addEventListener('click', function() {
            this.closest('.modal').classList.remove('active');
        });
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            e.target.classList.remove('active');
        }
    });
    
    // Filters
    categoryFilter.addEventListener('change', filterProducts);
    searchBox.addEventListener('input', filterProducts);
    
    // Checkout
    checkoutBtn.addEventListener('click', checkout);
    
    // Smooth scrolling for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
}

// Checkout function
async function checkout() {
    if (cart.length === 0) {
        alert('El carrito está vacío');
        return;
    }
    
    try {
        // Try to send order to API
        const response = await fetch('api/orders.php', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                items: cart,
                total: cart.reduce((sum, item) => sum + (item.price * item.quantity), 0)
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`¡Pedido realizado con éxito! Número de pedido: ${result.orderId}`);
        } else {
            throw new Error('API not available');
        }
    } catch (error) {
        // Fallback to demo mode
        console.log('Demo mode checkout:', error.message);
        alert('¡Pedido realizado con éxito! (Modo demostración)\n\nTotal: €' + 
              cart.reduce((sum, item) => sum + (item.price * item.quantity), 0).toFixed(2));
    }
    
    // Clear cart
    cart = [];
    updateCart();
    saveCartToStorage();
    closeModal('cart-modal');
}

// Close modal helper
function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

// Show notification
function showNotification(message) {
    // Create notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        background-color: var(--success-color);
        color: white;
        padding: 1rem 2rem;
        border-radius: 5px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        z-index: 1001;
        animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Local storage functions
function saveCartToStorage() {
    localStorage.setItem('vapes_shop_cart', JSON.stringify(cart));
}

function loadCartFromStorage() {
    const savedCart = localStorage.getItem('vapes_shop_cart');
    if (savedCart) {
        cart = JSON.parse(savedCart);
        updateCart();
    }
}

// Add CSS for notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
