// Rebuild first; build time is outside all benchmark timing and RSS workers.
await import('./build.mjs');
await import('./performance.mjs');
