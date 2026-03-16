import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve, join, extname } from 'path'
import { createReadStream, existsSync, statSync } from 'fs'

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.wav': 'audio/wav',
  '.ogg': 'audio/ogg',
  '.mp3': 'audio/mpeg',
  '.mp4': 'video/mp4',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
}

// storage/games 디렉토리를 /game 경로로 정적 서빙하는 플러그인
function serveGameFiles() {
  const storagePath = resolve(__dirname, '../../storage/games')
  return {
    name: 'serve-game-files',
    configureServer(server) {
      server.middlewares.use('/game', (req, res, next) => {
        const filePath = join(storagePath, decodeURIComponent(req.url))
        if (existsSync(filePath) && statSync(filePath).isFile()) {
          const ext = extname(filePath)
          res.setHeader('Content-Type', MIME_TYPES[ext] || 'application/octet-stream')
          createReadStream(filePath).pipe(res)
        } else {
          next()
        }
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), serveGameFiles()],
  envDir: resolve(__dirname, '../..'), // 루트 .env 참조
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
