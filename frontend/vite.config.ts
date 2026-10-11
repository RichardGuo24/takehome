import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server forwards /api to the FastAPI backend, so the browser sees one
// origin and no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
