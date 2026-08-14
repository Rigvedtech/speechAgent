/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_LANDING_ONLY: string
  /** Full-app request-access URL when VITE_LANDING_ONLY=true */
  readonly VITE_GET_STARTED_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
