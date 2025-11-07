# Node.js Dependencies for Web UI Development

## Prerequisites
- Node.js 18+ (LTS recommended)
- npm 9+ (comes with Node.js)

## Installation
```bash
npm install
```

## Dependencies

### Tailwind CSS v3
- **tailwindcss**: Utility-first CSS framework
- **postcss**: CSS transformation tool
- **autoprefixer**: Adds vendor prefixes automatically

### TypeScript
- **typescript**: TypeScript compiler for type-safe JavaScript

## Build Commands

### CSS Build
```bash
npm run build:css    # One-time build
npm run watch:css    # Watch mode for development
```

### TypeScript Build
```bash
npm run build:ts     # One-time build
npm run watch:ts     # Watch mode for development
```

### Combined Build
```bash
npm run build        # Build CSS and TypeScript
npm run watch        # Watch both CSS and TypeScript
```

## Project Structure
- `code/web/static/tailwind.css` - Tailwind entry point (source)
- `code/web/static/styles.css` - Generated CSS (git-ignored)
- `code/web/static/ts/` - TypeScript source files
- `code/web/static/js/` - Compiled JavaScript (git-ignored)

## Configuration Files
- `tailwind.config.js` - Tailwind CSS configuration
- `postcss.config.js` - PostCSS configuration
- `tsconfig.json` - TypeScript compiler configuration
- `package.json` - npm scripts and dependencies
