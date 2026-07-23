/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_LANDING_ONLY: string
  /** External Get Started URL when VITE_LANDING_ONLY=true (default https://rigvedtech.com) */
  readonly VITE_GET_STARTED_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
