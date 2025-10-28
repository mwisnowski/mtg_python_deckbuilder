/**
 * M2 Component Library - JavaScript Utilities
 * 
 * Core functions for interactive components:
 * - Card flip button (dual-faced cards)
 * - Collapsible panels
 * - Card popups
 * - Modal management
 */

// ============================================
// CARD FLIP FUNCTIONALITY
// ============================================

/**
 * Flip a dual-faced card image between front and back faces
 * @param {HTMLElement} button - The flip button element
 */
function flipCard(button) {
  const container = button.closest('.card-thumb-container, .card-popup-image');
  if (!container) return;
  
  const img = container.querySelector('img');
  if (!img) return;
  
  const cardName = img.dataset.cardName;
  if (!cardName) return;
  
  const faces = cardName.split(' // ');
  if (faces.length < 2) return;
  
  // Determine current face (default to 0 = front)
  const currentFace = parseInt(img.dataset.currentFace || '0', 10);
  const nextFace = currentFace === 0 ? 1 : 0;
  const faceName = faces[nextFace];
  
  // Determine image version based on container
  const isLarge = container.classList.contains('card-thumb-large') || 
                  container.classList.contains('card-popup-image');
  const version = isLarge ? 'normal' : 'small';
  
  // Update image source
  img.src = `https://api.scryfall.com/cards/named?fuzzy=${encodeURIComponent(faceName)}&format=image&version=${version}`;
  img.alt = `${faceName} image`;
  img.dataset.currentFace = nextFace.toString();
  
  // Update button aria-label
  const otherFace = faces[currentFace];
  button.setAttribute('aria-label', `Flip to ${otherFace}`);
}

/**
 * Reset all card images to show front face
 * Useful when navigating between pages or clearing selections
 */
function resetCardFaces() {
  document.querySelectorAll('img[data-card-name][data-current-face]').forEach(img => {
    const cardName = img.dataset.cardName;
    const faces = cardName.split(' // ');
    if (faces.length > 1) {
      const frontFace = faces[0];
      const container = img.closest('.card-thumb-container, .card-popup-image');
      const isLarge = container && (container.classList.contains('card-thumb-large') || 
                                    container.classList.contains('card-popup-image'));
      const version = isLarge ? 'normal' : 'small';
      
      img.src = `https://api.scryfall.com/cards/named?fuzzy=${encodeURIComponent(frontFace)}&format=image&version=${version}`;
      img.alt = `${frontFace} image`;
      img.dataset.currentFace = '0';
    }
  });
}

// ============================================
// COLLAPSIBLE PANEL FUNCTIONALITY
// ============================================

/**
 * Toggle a collapsible panel's expanded/collapsed state
 * @param {string} panelId - The ID of the panel element
 */
function togglePanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  
  const button = panel.querySelector('.panel-toggle');
  const content = panel.querySelector('.panel-collapse-content');
  if (!button || !content) return;
  
  const isExpanded = button.getAttribute('aria-expanded') === 'true';
  
  // Toggle state
  button.setAttribute('aria-expanded', (!isExpanded).toString());
  content.style.display = isExpanded ? 'none' : 'block';
  
  // Toggle classes
  panel.classList.toggle('panel-expanded', !isExpanded);
  panel.classList.toggle('panel-collapsed', isExpanded);
}

/**
 * Expand a collapsible panel
 * @param {string} panelId - The ID of the panel element
 */
function expandPanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  
  const button = panel.querySelector('.panel-toggle');
  const content = panel.querySelector('.panel-collapse-content');
  if (!button || !content) return;
  
  button.setAttribute('aria-expanded', 'true');
  content.style.display = 'block';
  panel.classList.add('panel-expanded');
  panel.classList.remove('panel-collapsed');
}

/**
 * Collapse a collapsible panel
 * @param {string} panelId - The ID of the panel element
 */
function collapsePanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  
  const button = panel.querySelector('.panel-toggle');
  const content = panel.querySelector('.panel-collapse-content');
  if (!button || !content) return;
  
  button.setAttribute('aria-expanded', 'false');
  content.style.display = 'none';
  panel.classList.add('panel-collapsed');
  panel.classList.remove('panel-expanded');
}

// ============================================
// MODAL MANAGEMENT
// ============================================

/**
 * Open a modal by ID
 * @param {string} modalId - The ID of the modal element
 */
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  
  // Focus first focusable element in modal
  const focusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  if (focusable) {
    setTimeout(() => focusable.focus(), 100);
  }
}

/**
 * Close a modal by ID or element
 * @param {string|HTMLElement} modalOrId - Modal element or ID
 */
function closeModal(modalOrId) {
  const modal = typeof modalOrId === 'string' 
    ? document.getElementById(modalOrId) 
    : modalOrId;
  
  if (!modal) return;
  
  modal.remove();
  
  // Restore body scroll if no other modals are open
  if (!document.querySelector('.modal')) {
    document.body.style.overflow = '';
  }
}

/**
 * Close all open modals
 */
function closeAllModals() {
  document.querySelectorAll('.modal').forEach(modal => modal.remove());
  document.body.style.overflow = '';
}

// ============================================
// CARD POPUP FUNCTIONALITY
// ============================================

/**
 * Show card details popup on hover or tap
 * @param {string} cardName - The card name
 * @param {Object} options - Popup options
 * @param {string[]} options.tags - Card tags
 * @param {string[]} options.highlightTags - Tags to highlight
 * @param {string} options.role - Card role
 * @param {string} options.layout - Card layout (for flip button)
 */
function showCardPopup(cardName, options = {}) {
  // Remove any existing popup
  closeCardPopup();
  
  const {
    tags = [],
    highlightTags = [],
    role = '',
    layout = 'normal'
  } = options;
  
  const isDFC = ['modal_dfc', 'transform', 'double_faced_token', 'reversible_card'].includes(layout);
  const baseName = cardName.split(' // ')[0];
  
  // Create popup HTML
  const popup = document.createElement('div');
  popup.className = 'card-popup';
  popup.setAttribute('role', 'dialog');
  popup.setAttribute('aria-label', `${cardName} details`);
  
  let tagsHTML = '';
  if (tags.length > 0) {
    tagsHTML = '<div class="card-popup-tags">';
    tags.forEach(tag => {
      const isHighlight = highlightTags.includes(tag);
      tagsHTML += `<span class="card-popup-tag${isHighlight ? ' card-popup-tag-highlight' : ''}">${tag}</span>`;
    });
    tagsHTML += '</div>';
  }
  
  let roleHTML = '';
  if (role) {
    roleHTML = `<div class="card-popup-role">Role: <span>${role}</span></div>`;
  }
  
  let flipButtonHTML = '';
  if (isDFC) {
    flipButtonHTML = `
      <button type="button" class="card-flip-btn" onclick="flipCard(this)" aria-label="Flip card">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M8 3.293l2.646 2.647.708-.708L8 2.879 4.646 5.232l.708.708L8 3.293zM8 12.707L5.354 10.06l-.708.708L8 13.121l3.354-2.353-.708-.708L8 12.707z"/>
        </svg>
      </button>
    `;
  }
  
  popup.innerHTML = `
    <div class="card-popup-backdrop" onclick="closeCardPopup()"></div>
    <div class="card-popup-content">
      <div class="card-popup-image">
        <img src="https://api.scryfall.com/cards/named?fuzzy=${encodeURIComponent(baseName)}&format=image&version=normal"
             alt="${cardName} image"
             data-card-name="${cardName}"
             loading="lazy"
             decoding="async" />
        ${flipButtonHTML}
      </div>
      <div class="card-popup-info">
        <h3 class="card-popup-name">${cardName}</h3>
        ${roleHTML}
        ${tagsHTML}
      </div>
      <button type="button" class="card-popup-close" onclick="closeCardPopup()" aria-label="Close">×</button>
    </div>
  `;
  
  document.body.appendChild(popup);
  document.body.style.overflow = 'hidden';
  
  // Focus close button
  const closeBtn = popup.querySelector('.card-popup-close');
  if (closeBtn) {
    setTimeout(() => closeBtn.focus(), 100);
  }
}

/**
 * Close card popup
 * @param {HTMLElement} [element] - Element to search from (optional)
 */
function closeCardPopup(element) {
  const popup = element 
    ? element.closest('.card-popup') 
    : document.querySelector('.card-popup');
  
  if (popup) {
    popup.remove();
    
    // Restore body scroll if no modals are open
    if (!document.querySelector('.modal')) {
      document.body.style.overflow = '';
    }
  }
}

/**
 * Setup card thumbnail hover/tap events
 * Call this after dynamically adding card thumbnails to the DOM
 */
function setupCardPopups() {
  document.querySelectorAll('.card-thumb-container[data-card-name]').forEach(container => {
    const img = container.querySelector('.card-thumb');
    if (!img) return;
    
    const cardName = container.dataset.cardName || img.dataset.cardName;
    if (!cardName) return;
    
    // Desktop: hover
    container.addEventListener('mouseenter', function(e) {
      if (window.innerWidth > 768) {
        const tags = (img.dataset.tags || '').split(',').map(t => t.trim()).filter(Boolean);
        const role = img.dataset.role || '';
        const layout = img.dataset.layout || 'normal';
        
        showCardPopup(cardName, { tags, highlightTags: [], role, layout });
      }
    });
    
    // Mobile: tap
    container.addEventListener('click', function(e) {
      if (window.innerWidth <= 768) {
        e.preventDefault();
        
        const tags = (img.dataset.tags || '').split(',').map(t => t.trim()).filter(Boolean);
        const role = img.dataset.role || '';
        const layout = img.dataset.layout || 'normal';
        
        showCardPopup(cardName, { tags, highlightTags: [], role, layout });
      }
    });
  });
}

// ============================================
// INITIALIZATION
// ============================================

// Setup event listeners when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    // Setup card popups on initial load
    setupCardPopups();
    
    // Close modals/popups on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeCardPopup();
        
        // Close topmost modal only
        const modals = document.querySelectorAll('.modal');
        if (modals.length > 0) {
          closeModal(modals[modals.length - 1]);
        }
      }
    });
  });
} else {
  // DOM already loaded
  setupCardPopups();
}

// Export functions for use in other scripts or inline handlers
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    flipCard,
    resetCardFaces,
    togglePanel,
    expandPanel,
    collapsePanel,
    openModal,
    closeModal,
    closeAllModals,
    showCardPopup,
    closeCardPopup,
    setupCardPopups
  };
}
