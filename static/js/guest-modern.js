// Modern Guest Interface JavaScript

class GuestApp {
    constructor() {
        this.cart = [];
        this.cartCount = 0;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadCart();
    }

    setupEventListeners() {
        // Add to cart buttons
        document.querySelectorAll('.add-to-cart-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.addToCart(e));
        });

        // Cart button
        const cartBtn = document.querySelector('.cart-button');
        if (cartBtn) {
            cartBtn.addEventListener('click', () => this.toggleCart());
        }

        // Category tabs
        document.querySelectorAll('.category-tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchCategory(e));
        });
    }

    addToCart(e) {
        const btn = e.currentTarget;
        const itemId = btn.dataset.itemId;
        const itemName = btn.dataset.itemName;
        const itemPrice = parseFloat(btn.dataset.itemPrice);

        // Add animation
        btn.innerHTML = '<i class="fas fa-check"></i> Added';
        btn.style.background = '#10b981';

        setTimeout(() => {
            btn.innerHTML = '<i class="fas fa-plus"></i> Add';
            btn.style.background = '';
        }, 1500);

        // Update cart
        this.cart.push({ id: itemId, name: itemName, price: itemPrice });
        this.cartCount++;
        this.updateCartBadge();
        this.showToast('Item added to cart!', 'success');
        this.saveCart();
    }

    updateCartBadge() {
        const badge = document.querySelector('.cart-badge');
        if (badge) {
            badge.textContent = this.cartCount;
            badge.style.display = this.cartCount > 0 ? 'flex' : 'none';
        }
    }

    toggleCart() {
        const modal = document.querySelector('.cart-modal');
        if (modal) {
            modal.classList.toggle('show');
        }
    }

    switchCategory(e) {
        const tab = e.currentTarget;
        const category = tab.dataset.category;

        // Update active tab
        document.querySelectorAll('.category-tab').forEach(t => {
            t.classList.remove('active');
        });
        tab.classList.add('active');

        // Filter items
        document.querySelectorAll('.menu-item-card').forEach(card => {
            const itemCategory = card.dataset.category;
            if (category === 'all' || itemCategory === category) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    }

    showToast(message, type = 'success') {
        const container = document.querySelector('.toast-container') || this.createToastContainer();
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
            <span>${message}</span>
        `;
        
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    createToastContainer() {
        const container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
        return container;
    }

    saveCart() {
        localStorage.setItem('guestCart', JSON.stringify(this.cart));
        localStorage.setItem('cartCount', this.cartCount);
    }

    loadCart() {
        const savedCart = localStorage.getItem('guestCart');
        const savedCount = localStorage.getItem('cartCount');
        
        if (savedCart) {
            this.cart = JSON.parse(savedCart);
        }
        if (savedCount) {
            this.cartCount = parseInt(savedCount);
            this.updateCartBadge();
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.guestApp = new GuestApp();
});

// Smooth scroll for navigation
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Pull to refresh (mobile)
let touchStartY = 0;
let touchEndY = 0;

document.addEventListener('touchstart', e => {
    touchStartY = e.changedTouches[0].screenY;
}, { passive: true });

document.addEventListener('touchend', e => {
    touchEndY = e.changedTouches[0].screenY;
    handleSwipe();
}, { passive: true });

function handleSwipe() {
    if (touchEndY - touchStartY > 100 && window.scrollY === 0) {
        location.reload();
    }
}
