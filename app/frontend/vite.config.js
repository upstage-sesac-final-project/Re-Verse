import { defineConfig } from 'vite'
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
// 프로젝트별 파일(data/) 없으면 base_game으로 fallback
function serveGameFiles() {
  const storagePath = resolve(__dirname, '../../storage/games')
  const baseGamePath = resolve(__dirname, '../../storage/games/base_game')

  function serveFile(filePath, res) {
    const ext = extname(filePath)
    res.setHeader('Content-Type', MIME_TYPES[ext] || 'application/octet-stream')
    createReadStream(filePath).pipe(res)
  }

  return {
    name: 'serve-game-files',
    configureServer(server) {
      server.middlewares.use('/game', (req, res, next) => {
        const urlPath = decodeURIComponent(req.url.split('?')[0]).replace(/^\//, '')
        const slashIdx = urlPath.indexOf('/')
        if (slashIdx === -1) return next()

        const gameId = urlPath.slice(0, slashIdx)
        const filePart = urlPath.slice(slashIdx + 1) || 'index.html'

        // 1) 프로젝트별 파일 (data/ JSON 등)
        const projectFile = resolve(join(storagePath, gameId, filePart))
        if (projectFile.startsWith(storagePath + sep) && existsSync(projectFile) && statSync(projectFile).isFile()) {
          return serveFile(projectFile, res)
        }

        // 2) base_game 공유 에셋 fallback (img, js, css, audio 등)
        const baseFile = resolve(join(baseGamePath, filePart))
        if (baseFile.startsWith(baseGamePath + sep) && existsSync(baseFile) && statSync(baseFile).isFile()) {
          return serveFile(baseFile, res)
        }

        next()
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
      // 새로 추가 - docker로 프론트/백엔드 같이 띄울 때 필요한 설정
      '/game': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
