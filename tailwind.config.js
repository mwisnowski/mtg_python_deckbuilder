/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./code/web/templates/**/*.html",
    "./code/web/static/**/*.js",
    "./code/web/static/**/*.ts",
  ],
  theme: {
    extend: {
      colors: {
        // MTG color identity colors
        'mtg-white': '#F8F6D8',
        'mtg-blue': '#0E68AB',
        'mtg-black': '#150B00',
        'mtg-red': '#D3202A',
        'mtg-green': '#00733E',
        
        // Theme colors (match existing CSS variables)
        'bg-primary': 'var(--bg-primary)',
        'bg-secondary': 'var(--bg-secondary)',
        'bg-tertiary': 'var(--bg-tertiary)',
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'border-color': 'var(--border-color)',
        'accent-primary': 'var(--accent-primary)',
        'accent-secondary': 'var(--accent-secondary)',
        'panel-bg': 'var(--panel-bg)',
        'panel-border': 'var(--panel-border)',
        
        // Button colors
        'btn-forward': '#3b82f6', // blue
        'btn-backward': '#6b7280', // gray
      },
      spacing: {
        // Card image sizes
        'card-prominent': '360px',
        'card-list': '160px',
      },
      zIndex: {
        // Z-index stacking system
        'base': '0',
        'dropdown': '10',
        'sticky': '20',
        'modal-backdrop': '40',
        'modal': '50',
        'toast': '60',
        'tooltip': '70',
      },
    },
    screens: {
      'mobile-max': {'max': '900px'},
    },
  },
  plugins: [],
}
