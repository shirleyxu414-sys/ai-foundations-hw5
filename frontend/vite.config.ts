import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The backend allows this exact origin (http://localhost:5173), so the port must not drift.
  server: { port: 5173, strictPort: true, open: true },
})
