# 🚀 Re:Verse 배포 가이드 (최종 검증 완료)

> **프론트엔드(Vercel) + 백엔드(EC2 Docker) 분리 배포 환경**  
> Mixed Content 문제 해결 및 프로덕션 보안 설정 완료

## 📋 배포 아키텍처

```
사용자 브라우저 (HTTPS)
    ↓
Vercel (프론트엔드) - HTTPS 정적 호스팅 + Proxy
    ↓ Vercel Rewrites (Mixed Content 해결)
EC2 (백엔드 Docker) - FastAPI + uvicorn
    ↓
Supabase/External APIs (데이터베이스 & AI 서비스)
```

### 🎯 환경별 구성

| 환경 | 프론트엔드 | 백엔드 | 사용 명령어 |
|------|------------|--------|-------------|
| **로컬 개발** | Docker (개발서버) 또는 별도 실행 | Docker (볼륨 마운트) | `docker compose up -d` |
| **프로덕션** | Vercel (자동 빌드) | EC2 Docker (최적화) | `vercel` + EC2 배포 |

---

## 🛠 1단계: EC2 백엔드 배포

### EC2 인스턴스 준비
```bash
# EC2 접속 후
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 프로젝트 배포
```bash
# 프로젝트 클론
git clone https://github.com/your-username/Re-Verse.git
cd Re-Verse

# 환경변수 설정 (.env 파일이 없으면 생성)
# 현재 .env 파일 기반으로 필요한 값들 확인
cat .env  # 현재 설정된 값들 확인

# 프로덕션 배포 (백엔드만)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 상태 확인
docker compose ps
docker compose logs -f backend

# 헬스체크 테스트
curl http://localhost:8000/health
# 예상 응답: {"status":"healthy","message":"Re:Verse Backend is running"}
```

### EC2 보안 그룹 설정
- **인바운드 규칙 추가**: 포트 8000 (HTTP) 전체 허용 (0.0.0.0/0)
- **아웃바운드 규칙**: 전체 허용 (기본값)

---

## 🌐 2단계: Vercel 프론트엔드 배포

### 📝 중요: vercel.json EC2 IP 설정
배포 전에 `vercel.json`에서 **YOUR-EC2-IP**를 실제 EC2 탄력적 IP로 변경해야 합니다:

```bash
# EC2 탄력적 IP 확인 (EC2 콘솔에서)
# 예: 13.125.123.45

# vercel.json 수정
vim vercel.json
# 또는 에디터에서 다음 부분 수정:
```

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "http://13.125.123.45:8000/api/:path*"  // 👈 실제 EC2 IP로 변경
    }
  ]
}
```

### 🚀 Vercel CLI 배포
```bash
# 1. Vercel CLI 설치
npm install -g vercel

# 2. Vercel 로그인
vercel login

# 3. 프로젝트 루트에서 첫 배포 (대화형)
vercel

# 첫 배포 시 질문들:
# - Set up and deploy "Re-Verse"? [Y/n] → Y
# - Which scope? → 본인 계정 선택
# - Link to existing project? [y/N] → N (새 프로젝트)
# - What's your project's name? → re-verse (또는 원하는 이름)
# - In which directory is your code located? → ./

# 4. 프로덕션 배포
vercel --prod

# 5. 배포 완료 후 URL 확인
# 예: https://re-verse-abc123.vercel.app
```

### ✅ Vercel 대시보드 확인사항
1. **배포 상태**: https://vercel.com/dashboard → 프로젝트 선택
2. **환경변수**: Settings → Environment Variables
   - `VITE_API_URL` = `/api` (자동 설정됨)
3. **빌드 로그**: Deployments 탭에서 빌드 성공 확인
4. **도메인**: Settings → Domains에서 커스텀 도메인 설정 가능

---

## 🔧 Mixed Content 해결 원리

### ❌ 잘못된 방식 (Mixed Content 에러)
```javascript
// 브라우저에서 직접 EC2로 요청 - 보안상 차단됨!
fetch('http://13.125.123.45:8000/api/users')  // HTTPS → HTTP 차단
// 🚫 Error: Mixed Content blocked by browser
```

### ✅ 올바른 방식 (Vercel Proxy 사용)
```javascript
// 1. 프론트엔드 코드에서 상대 경로 사용
fetch('/api/users')  // 브라우저가 같은 도메인으로 인식

// 2. 실제 통신 흐름:
// 브라우저 → https://your-app.vercel.app/api/users (HTTPS ✅)
//           ↓ Vercel rewrites 규칙
//         → http://13.125.123.45:8000/api/users (서버간 통신 ✅)
//           ↓ EC2 FastAPI 응답
//         → https://your-app.vercel.app (HTTPS로 브라우저에 전달 ✅)

// 3. 브라우저는 HTTPS 통신만 하므로 안전함
```

### 🛡️ 보안 효과
- **IP 숨김**: 프론트엔드에서 EC2 IP 직접 노출 안 됨
- **DDoS 방어**: Vercel CDN이 1차 방어
- **SSL 종단**: 브라우저-Vercel 간만 HTTPS 필요

---

---

## 🧪 로컬 개발 환경 사용법

### 🖥️ 백엔드만 실행 (권장)
```bash
# 백엔드만 Docker로 실행
docker compose up -d

# 로그 확인
docker compose logs -f backend

# 테스트
curl http://localhost:8000/health
curl http://localhost:8000/docs  # FastAPI 문서

# 중지
docker compose down
```

### 🎨 프론트엔드 + 백엔드 함께 실행
```bash
# 전체 개발 환경 (프론트엔드 개발서버 포함)
docker compose --profile full-dev up -d

# 접속
# - 백엔드: http://localhost:8000
# - 프론트엔드: http://localhost:3000

# 개별 서비스 로그
docker compose logs -f backend
docker compose logs -f frontend-dev
```

### 🔄 개발 중 코드 변경
로컬 환경에서는 볼륨 마운트가 설정되어 있어 **코드 변경이 자동 반영**됩니다:
- **백엔드**: `app/backend/` 폴더 수정 → 컨테이너 자동 반영
- **프론트엔드**: `app/frontend/src/` 폴더 수정 → 핫 리로드

### 🛠️ 개발 도구 사용법
```bash
# 개발 의존성 설치 (ruff, mypy, pytest 등)
uv sync --extra dev

# 코드 스타일 체크 및 자동 수정
uv run ruff check app/backend --fix

# 타입 체크
uv run mypy app/backend

# 테스트 실행
uv run pytest app/backend/tests

# 모든 검사 한 번에 실행
uv run ruff check app/backend --fix && uv run mypy app/backend && uv run pytest app/backend/tests
```

---

## 📝 배포 체크리스트

### ✅ EC2 백엔드 배포 전 준비
- [ ] **EC2 인스턴스**: t3.small 이상 권장 (1GB+ 메모리)
- [ ] **보안그룹**: 인바운드 8000 포트 열기 (0.0.0.0/0)
- [ ] **탄력적 IP**: 고정 IP 할당 (Vercel에서 사용)
- [ ] **Docker 설치**: EC2에 Docker + Docker Compose 설치 완료

### ✅ EC2 백엔드 배포 후 확인
- [ ] `docker compose ps` → backend 상태 Up
- [ ] `curl http://localhost:8000/health` → {"status":"healthy"} 응답
- [ ] `curl http://<EC2-IP>:8000/health` → 외부 접근 확인
- [ ] `docker compose logs backend` → 오류 없이 실행 확인
- [ ] EC2 보안그룹 8000 포트 열림 재확인

### ✅ Vercel 프론트엔드 배포 전 준비  
- [ ] `vercel.json`에 실제 EC2 탄력적 IP 입력
- [ ] Vercel CLI 설치 및 로그인 완료
- [ ] `app/frontend/` 경로에 React 프로젝트 존재 확인

### ✅ Vercel 프론트엔드 배포 후 확인
- [ ] Vercel 대시보드에서 빌드 성공 확인
- [ ] 배포된 URL에서 프론트엔드 정상 로드
- [ ] 브라우저 개발자 도구 → Network 탭에서 `/api` 호출 성공
- [ ] Console에 CORS 에러나 Mixed Content 에러 없음

---

---

## 🐛 트러블슈팅 가이드

### 🚨 1. "API 호출이 안 돼요!" 
**증상**: 프론트엔드에서 API 요청 시 오류 발생

**확인 순서**:
```bash
# A. EC2 백엔드 상태 확인
docker compose ps
docker compose logs -f backend

# B. 직접 API 테스트
curl http://<EC2-IP>:8000/health
curl http://<EC2-IP>:8000/docs

# C. Vercel 프록시 테스트 (배포된 사이트에서 개발자 도구)
fetch('/api/health').then(r => r.json()).then(console.log)
```

**해결법**:
- EC2 보안그룹 8000 포트 열기
- `vercel.json`에 올바른 EC2 IP 설정
- 백엔드 컨테이너 재시작: `docker compose restart backend`

### ⚠️ 2. CORS 에러 발생
**증상**: "Access to fetch blocked by CORS policy"

**현재 설정 확인**:
```python
# app/backend/main.py에 이미 설정됨
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 로컬
        "https://*.vercel.app",   # Vercel
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**해결법**: 실제 Vercel URL을 CORS에 추가
```python
allow_origins=[
    "https://your-actual-app.vercel.app",  # 실제 배포 URL
    "https://*.vercel.app",
]
```

### 🔧 3. 환경변수 문제
```bash
# EC2에서 환경변수 확인
docker compose exec backend env | grep -E "(UPSTAGE|SUPABASE|ENVIRONMENT)"

# Vercel 환경변수 확인
vercel env ls

# 환경변수 추가 (Vercel)
vercel env add VITE_API_URL
# Value: /api
```

### 🐳 4. Docker 관련 문제
```bash
# 컨테이너 상태 확인
docker compose ps

# 전체 재시작
docker compose down
docker compose up -d

# 이미지 재빌드 (코드 변경 시)
docker compose up -d --build

# 로그에서 에러 찾기
docker compose logs backend | grep -i error
```

### 🌐 5. Vercel 빌드 실패
**Vercel 대시보드 → Deployments → 실패한 배포 클릭**

**자주 발생하는 원인**:
- `app/frontend/package.json`의 의존성 문제
- `vercel.json`의 경로 오류
- 환경변수 누락

**해결법**:
```bash
# 로컬에서 빌드 테스트
cd app/frontend
npm install
npm run build

# 문제없으면 재배포
vercel --prod
```

---

## 📊 배포 완료 후 테스트

### 🧪 1. 백엔드 API 직접 테스트
```bash
# 헬스체크 (EC2에서 로컬)
curl http://localhost:8000/health
# 예상: {"status":"healthy","message":"Re:Verse Backend is running"}

# 헬스체크 (외부에서)
curl http://<EC2-IP>:8000/health

# FastAPI 문서 접근
curl http://<EC2-IP>:8000/docs
# 또는 브라우저에서: http://<EC2-IP>:8000/docs

# JSON 응답 확인
curl http://<EC2-IP>:8000/ | jq
```

### 🌐 2. Vercel 프록시를 통한 API 테스트
**배포된 Vercel 사이트에서 개발자 도구 열고:**
```javascript
// F12 → Console에서 실행
fetch('/api/health')
  .then(r => r.json())
  .then(data => console.log('✅ 프록시 성공:', data))
  .catch(err => console.error('❌ 프록시 실패:', err))

// 예상 성공 응답:
// ✅ 프록시 성공: {status: "healthy", message: "Re:Verse Backend is running"}
```

### 🔍 3. 전체 통신 플로우 검증
1. **Vercel 앱 접속**: `https://your-app.vercel.app`
2. **개발자 도구**: F12 → Network 탭 열기
3. **API 테스트**: 앱에서 API 호출하는 기능 실행
4. **네트워크 확인**: 
   - `/api/*` 요청들이 **200 OK** 상태
   - **Response Headers**에서 `access-control-allow-origin` 확인
   - **Mixed Content 에러 없음** 확인

### ✅ 4. 성공 확인 지표
- [ ] EC2: `curl http://<EC2-IP>:8000/health` → 200 OK
- [ ] Vercel: 사이트 정상 로드
- [ ] Proxy: `fetch('/api/health')` → 200 OK  
- [ ] CORS: Console에 CORS 에러 없음
- [ ] Logs: `docker compose logs backend` → 정상 요청 로그

---

## 🚀 배포 자동화 및 확장

### 📦 GitHub Actions CI/CD (향후 계획)
```yaml
# .github/workflows/deploy.yml 예시
name: Deploy to Production
on:
  push:
    branches: [main]
jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to EC2
        # EC2에 SSH 접속하여 docker compose 재배포
  
  deploy-frontend:
    runs-on: ubuntu-latest  
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Vercel
        # Vercel CLI로 자동 배포
```

### 🔧 성능 최적화 옵션
- **EC2**: ALB + 다중 인스턴스, Auto Scaling
- **Vercel**: Edge Functions, ISR (Incremental Static Regeneration)
- **Database**: Supabase 커넥션 풀링
- **Monitoring**: CloudWatch + Vercel Analytics

### 🛡️ 보안 강화
- **SSL**: Let's Encrypt 자동 갱신
- **방화벽**: EC2 Security Groups 세밀한 설정
- **API**: Rate Limiting, JWT 토큰 인증
- **Secrets**: AWS Secrets Manager 또는 Vercel Environment Variables

---

## 🎉 배포 완료!

이제 **Mixed Content 문제 없이** 프론트엔드(Vercel)와 백엔드(EC2)가 안전하게 통신하는 프로덕션 환경이 준비되었습니다!

**📞 문제 발생 시**: 위의 트러블슈팅 가이드를 참고하거나 로그를 확인해 주세요.