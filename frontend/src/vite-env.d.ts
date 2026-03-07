/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MCQ_API_URL?: string
  readonly VITE_API_URL?: string
  readonly VITE_PAPERS_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
