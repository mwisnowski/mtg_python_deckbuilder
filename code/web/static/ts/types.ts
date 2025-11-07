/* Shared TypeScript type definitions for MTG Deckbuilder web app */

// Toast system types
export interface ToastOptions {
  duration?: number;
}

// State management types
export interface StateManager {
  get(key: string, def?: any): any;
  set(key: string, val: any): void;
  inHash(obj: Record<string, any>): void;
  readHash(): URLSearchParams;
}

// Telemetry types
export interface TelemetryManager {
  send(eventName: string, data?: Record<string, any>): void;
}

// Skeleton system types
export interface SkeletonManager {
  show(context?: HTMLElement | Document): void;
  hide(context?: HTMLElement | Document): void;
}

// Card popup types (from components.ts)
export interface CardPopupOptions {
  tags?: string[];
  highlightTags?: string[];
  role?: string;
  layout?: string;
  showActions?: boolean;
}

// HTMX event detail types
export interface HtmxResponseErrorDetail {
  xhr?: XMLHttpRequest;
  path?: string;
  target?: HTMLElement;
}

export interface HtmxEventDetail {
  target?: HTMLElement;
  elt?: HTMLElement;
  path?: string;
  xhr?: XMLHttpRequest;
}

// HTMX cache interface
export interface HtmxCache {
  get(key: string): any;
  set(key: string, html: string, ttl?: number, meta?: any): void;
  apply(elt: any, detail: any, entry: any): void;
  buildKey(detail: any, elt: any): string;
  ttlFor(elt: any): number;
  prefetch(url: string, opts?: any): void;
}

// Global window extensions
declare global {
  interface Window {
    __mtgState: StateManager;
    toast: (msg: string | HTMLElement, type?: string, opts?: ToastOptions) => HTMLElement;
    toastHTML: (html: string, type?: string, opts?: ToastOptions) => HTMLElement;
    appTelemetry: TelemetryManager;
    skeletons: SkeletonManager;
    __telemetryEndpoint?: string;
    showCardPopup?: (cardName: string, options?: CardPopupOptions) => void;
    dismissCardPopup?: () => void;
    flipCard?: (button: HTMLElement) => void;
    htmxCache?: HtmxCache;
    htmx?: any; // HTMX library - use any for external library
    initHtmxDebounce?: () => void;
    scrollCardIntoView?: (card: HTMLElement) => void;
    __virtGlobal?: any;
    __virtHotkeyBound?: boolean;
  }

  interface CustomEvent<T = any> {
    readonly detail: T;
  }

  // HTMX custom events
  interface DocumentEventMap {
    'htmx:responseError': CustomEvent<HtmxResponseErrorDetail>;
    'htmx:sendError': CustomEvent<any>;
    'htmx:afterSwap': CustomEvent<HtmxEventDetail>;
    'htmx:beforeRequest': CustomEvent<HtmxEventDetail>;
    'htmx:afterSettle': CustomEvent<HtmxEventDetail>;
    'htmx:afterRequest': CustomEvent<HtmxEventDetail>;
  }

  interface HTMLElement {
    __hxCacheKey?: string;
    __hxCacheTTL?: number;
  }
  
  interface Element {
    __hxPrefetched?: boolean;
  }
}

// Empty export to make this a module file
export {};
