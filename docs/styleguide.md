# MTG Deckbuilder Web UI Style Guide

## Design Tokens

Design tokens provide a consistent foundation for all UI elements. These are defined as CSS custom properties in `code/web/static/styles.css`.

### Spacing Scale

Use the spacing scale for margins, padding, and gaps:

```css
--space-xs: 0.25rem;  /* 4px  - Tight spacing within components */
--space-sm: 0.5rem;   /* 8px  - Default gaps between small elements */
--space-md: 0.75rem;  /* 12px - Standard component padding */
--space-lg: 1rem;     /* 16px - Section spacing, card gaps */
--space-xl: 1.5rem;   /* 24px - Major section breaks */
--space-2xl: 2rem;    /* 32px - Page-level spacing */
```

**Usage examples:**
- Chip gaps: `gap: var(--space-sm)`
- Panel padding: `padding: var(--space-md)`
- Section margins: `margin: var(--space-xl) 0`

### Typography Scale

Consistent font sizes for hierarchy:

```css
--text-xs: 0.75rem;   /* 12px - Meta info, badges */
--text-sm: 0.875rem;  /* 14px - Secondary text */
--text-base: 1rem;    /* 16px - Body text */
--text-lg: 1.125rem;  /* 18px - Subheadings */
--text-xl: 1.25rem;   /* 20px - Section headers */
--text-2xl: 1.5rem;   /* 24px - Page titles */
```

**Font weights:**
```css
--font-normal: 400;   /* Body text */
--font-medium: 500;   /* Emphasis */
--font-semibold: 600; /* Headings */
--font-bold: 700;     /* Strong emphasis */
```

### Border Radius

Consistent corner rounding:

```css
--radius-sm: 4px;     /* Subtle rounding */
--radius-md: 6px;     /* Buttons, inputs */
--radius-lg: 8px;     /* Panels, cards */
--radius-xl: 12px;    /* Large containers */
--radius-full: 999px; /* Pills, chips */
```

### Color Tokens

#### Semantic Colors
```css
--bg: #0f0f10;        /* Page background */
--panel: #1a1b1e;     /* Panel/card backgrounds */
--text: #e8e8e8;      /* Primary text */
--muted: #b6b8bd;     /* Secondary text */
--border: #2a2b2f;    /* Borders and dividers */
--ring: #60a5fa;      /* Focus indicator */
--ok: #16a34a;        /* Success states */
--warn: #f59e0b;      /* Warning states */
--err: #ef4444;       /* Error states */
```

#### MTG Color Identity
```css
--green-main: rgb(0,115,62);
--green-light: rgb(196,211,202);
--blue-main: rgb(14,104,171);
--blue-light: rgb(179,206,234);
--red-main: rgb(211,32,42);
--red-light: rgb(235,159,130);
--white-main: rgb(249,250,244);
--white-light: rgb(248,231,185);
--black-main: rgb(21,11,0);
--black-light: rgb(166,159,157);
```

## Component Patterns

### Chips

Chips display tags, status indicators, and metadata.

**Basic chip:**
```html
<span class="chip">
  <span class="dot" style="background: var(--ok);"></span>
  Label
</span>
```

**Chip containers:**
```html
<!-- Flexbox inline chips (existing) -->
<div class="chips-inline">
  <span class="chip">Tag 1</span>
  <span class="chip">Tag 2</span>
</div>

<!-- Grid auto-fit chips (new - responsive) -->
<div class="chips-grid">
  <span class="chip">Item 1</span>
  <span class="chip">Item 2</span>
  <span class="chip">Item 3</span>
</div>

<!-- Small grid (90px min) -->
<div class="chips-grid chips-grid-sm">...</div>

<!-- Large grid (160px min) -->
<div class="chips-grid chips-grid-lg">...</div>
```

### Summary Panels

Responsive grid panels for dashboard-style layouts:

```html
<div class="summary-panels">
  <div class="summary-panel">
    <div class="summary-panel-header">Panel Title</div>
    <div class="summary-panel-content">
      Panel content here
    </div>
  </div>
  <div class="summary-panel">
    <div class="summary-panel-header">Another Panel</div>
    <div class="summary-panel-content">
      More content
    </div>
  </div>
</div>
```

Panels automatically flow into columns based on available width (240px min per column).

## Responsive Breakpoints

The UI uses CSS Grid `auto-fit` patterns that adapt naturally to viewport width:

- **Mobile** (< 640px): Single column layouts
- **Tablet** (640px - 900px): 2-column where space allows
- **Desktop** (> 900px): Multi-column with `auto-fit`

Grid patterns automatically adjust without media queries:
```css
grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
```

## Accessibility

### Focus Indicators
All interactive elements receive a visible focus ring:
```css
.focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
```

### Color Contrast
- Text on backgrounds: Minimum 4.5:1 ratio (WCAG AA)
- Large text/headings: Minimum 3:1 ratio
- Interactive elements: Sufficient contrast for all states

### Keyboard Navigation
- Tab order follows visual flow
- Skip links available for main content areas
- All controls accessible via keyboard

## Theme Support

The app supports multiple themes via `data-theme` attribute:

- `dark` (default): Dark mode optimized
- `light-blend`: Light mode with warm tones
- `high-contrast`: Maximum contrast for visibility
- `cb-friendly`: Color-blind friendly palette

Themes automatically adjust all token values.

## Best Practices

1. **Use tokens over hardcoded values**
   - ✅ `padding: var(--space-md)`
   - ❌ `padding: 12px`

2. **Leverage auto-fit grids for responsive layouts**
   - ✅ `grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))`
   - ❌ Multiple media queries with fixed columns

3. **Maintain semantic color usage**
   - Use `--ok`, `--warn`, `--err` for states
   - Use MTG colors for identity-specific UI
   - Use `--text`, `--muted` for typography hierarchy

4. **Keep components DRY**
   - Reuse `.chip`, `.summary-panel`, `.chips-grid` patterns
   - Extend with modifiers, not duplicates

5. **Test across viewports**
   - Verify auto-fit breakpoints work smoothly
   - Check mobile (375px), tablet (768px), desktop (1440px)
