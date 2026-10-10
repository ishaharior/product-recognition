/// <reference types="vite/client" />

/**
 * Ambient declarations needed without touching the contract files:
 * - `vite/client` provides `import.meta.env` (used by services/api.ts) and
 *   `declare module '*.css'` for stylesheet imports.
 * - `services/api.ts` references the `Scan` type without importing it, so the
 *   shared type is exposed globally here.
 */
type Scan = import('./types').Scan;
