import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve, join, extname, sep } from 'path'
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
        const urlPath = decodeURIComponent(req.url.split('?')[0])
        const filePath = resolve(join(storagePath, urlPath))
        if (!filePath.startsWith(storagePath + sep) && filePath !== storagePath) {
          return next()
        }
        if (existsSync(filePath) && statSync(filePath).isFile()) {
          const ext = extname(filePath)
          res.setHeader('Content-Type', MIME_TYPES[ext] || 'application/octet-stream')
          if (ext === '.json' || ext === '.html') {
            res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate')
          }
          createReadStream(filePath).pipe(res)
        } else {
          next()
        }
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const root = resolve(__dirname, '../..')
  const env = loadEnv(mode, root, '')
  // 호스트에서 npm run dev: 127.0.0.1 (backend 호스트·도커 8000 포트)
  // docker compose frontend-dev: 환경변수로 http://backend:8000 주입
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react(), serveGameFiles()],
    envDir: root,
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
        // 로컬에 파일이 없을 때(또는 compose 안 프론트) 백엔드 StaticFiles로 폴백
        '/game': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
