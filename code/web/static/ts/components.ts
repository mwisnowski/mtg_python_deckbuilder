/**
 * M3 Component Library - TypeScript Utilities
 * 
 * Core functions for interactive components:
 * - Card flip button (dual-faced cards)
 * - Collapsible panels
 * - Card popups
 * - Modal management
 * 
 * Migrated from components.js with TypeScript types
 */

// ============================================
// TYPE DEFINITIONS
// ============================================

interface CardPopupOptions {
  tags?: string[];
  highlightTags?: string[];
  role?: string;
  layout?: string;
}

// ============================================
// CARD FLIP FUNCTIONALITY
// ============================================

/**
 * Flip a dual-faced card image between front and back faces
 * @param button - The flip button element
 */
function flipCard(button: HTMLElement): void {
  const container = button.closest('.card-thumb-container, .card-popup-image') as HTMLElement | null;
  if (!container) return;
  
  const img = container.querySelector('img') as HTMLImageElement | null;
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
function resetCardFaces(): void {
  document.querySelectorAll<HTMLImageElement>('img[data-card-name][data-current-face]').forEach(img => {
    const cardName = img.dataset.cardName;
    if (!cardName) return;
    
    const faces = cardName.split(' // ');
    if (faces.length > 1) {
      const frontFace = faces[0];
      const container = img.closest('.card-thumb-container, .card-popup-image') as HTMLElement | null;
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
 * @param panelId - The ID of the panel element
 */
function togglePanel(panelId: string): void {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  
  const button = panel.querySelector('.panel-toggle') as HTMLElement | null;
  const content = panel.querySelector('.panel-collapse-content') as HTMLElement | null;
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
 * @param panelId - The ID of the panel element
 */
function expandPanel(panelId: string): void {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  
  const button = panel.querySelector('.panel-toggle') as HTMLElement | null;
  const content = panel.querySelector('.panel-collapse-content') as HTMLElement | null;
  if (!button || !content) return;
  
  button.setAttribute('aria-expanded', 'true');
  content.style.display = 'block';
  panel.classList.add('panel-expanded');
  panel.classList.remove('panel-collapsed');
}

/**
 * Collapse a collapsible panel
 * @param panelId - The ID of the panel element
 */
function collapsePanel(panelId: string): void {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  
  const button = panel.querySelector('.panel-toggle') as HTMLElement | null;
  const content = panel.querySelector('.panel-collapse-content') as HTMLElement | null;
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
 * @param modalId - The ID of the modal element
 */
function openModal(modalId: string): void {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  
  (modal as HTMLElement).style.display = 'flex';
  document.body.style.overflow = 'hidden';
  
  // Focus first focusable element in modal
  const focusable = modal.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  if (focusable) {
    setTimeout(() => focusable.focus(), 100);
  }
}

/**
 * Close a modal by ID or element
 * @param modalOrId - Modal element or ID
 */
function closeModal(modalOrId: string | HTMLElement): void {
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
function closeAllModals(): void {
  document.querySelectorAll('.modal').forEach(modal => modal.remove());
  document.body.style.overflow = '';
}

// ============================================
// CARD POPUP FUNCTIONALITY
// ============================================

/**
 * Show card details popup on hover or tap
 * @param cardName - The card name
 * @param options - Popup options
 */
function showCardPopup(cardName: string, options: CardPopupOptions = {}): void {
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
  const closeBtn = popup.querySelector<HTMLElement>('.card-popup-close');
  if (closeBtn) {
    setTimeout(() => closeBtn.focus(), 100);
  }
}

/**
 * Close card popup
 * @param element - Element to search from (optional)
 */
function closeCardPopup(element?: HTMLElement): void {
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
function setupCardPopups(): void {
  document.querySelectorAll<HTMLElement>('.card-thumb-container[data-card-name]').forEach(container => {
    const img = container.querySelector<HTMLElement>('.card-thumb');
    if (!img) return;
    
    const cardName = container.dataset.cardName || img.dataset.cardName;
    if (!cardName) return;
    
    // Desktop: hover
    container.addEventListener('mouseenter', function(e: MouseEvent) {
      if (window.innerWidth > 768) {
        const tags = (img.dataset.tags || '').split(',').map(t => t.trim()).filter(Boolean);
        const role = img.dataset.role || '';
        const layout = img.dataset.layout || 'normal';
        
        showCardPopup(cardName, { tags, highlightTags: [], role, layout });
      }
    });
    
    // Mobile: tap
    container.addEventListener('click', function(e: MouseEvent) {
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
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeCardPopup();
        
        // Close topmost modal only
        const modals = document.querySelectorAll('.modal');
        if (modals.length > 0) {
          closeModal(modals[modals.length - 1] as HTMLElement);
        }
      }
    });
  });
} else {
  // DOM already loaded
  setupCardPopups();
}

// Make functions globally available for inline onclick handlers
(window as any).flipCard = flipCard;
(window as any).resetCardFaces = resetCardFaces;
(window as any).togglePanel = togglePanel;
(window as any).expandPanel = expandPanel;
(window as any).collapsePanel = collapsePanel;
(window as any).openModal = openModal;
(window as any).closeModal = closeModal;
(window as any).closeAllModals = closeAllModals;
(window as any).showCardPopup = showCardPopup;
(window as any).closeCardPopup = closeCardPopup;
(window as any).setupCardPopups = setupCardPopups;
