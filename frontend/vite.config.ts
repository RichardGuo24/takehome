import react from '@vitejs/plugin-react'
import { defineConfig, searchForWorkspaceRoot } from 'vite'

// The dev server forwards /api to the FastAPI backend, so the browser sees one
// origin and no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
    // The dashboard imports the spec's sample JSON straight from backend/samples,
    // so there is one copy of it. Vite only serves files under the project root
    // unless they are listed here.
    fs: {
      allow: [searchForWorkspaceRoot(process.cwd()), '../backend/samples'],
    },
  },
})
