# Re:Verse Frontend - 로컬 개발용만 (Vercel 배포 시에는 미사용)
# Vercel로 배포할 때는 이 파일 대신 Vercel이 자동으로 빌드함
# 로컬 개발 시에만 사용

FROM node:20-alpine

WORKDIR /app

COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci

COPY app/frontend ./

# 로컬 개발용 환경변수 (백엔드를 localhost:8000으로)
ENV VITE_API_URL=http://localhost:8000/api

EXPOSE 3000

# 개발 서버 실행
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]