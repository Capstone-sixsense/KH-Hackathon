# ── 프론트엔드 Dockerfile (Flutter Web + nginx) ──────────────────────────

# ── Stage 1: Flutter Web 빌드 ──
FROM ghcr.io/cirruslabs/flutter:stable AS builder

WORKDIR /app

ARG API_BASE_URL=http://localhost:8000
ENV API_BASE_URL=$API_BASE_URL

# 의존성 먼저 (캐시 최적화)
COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

# 소스 전체 복사 후 Web 빌드
COPY . .
RUN flutter build web --release \
    --dart-define=API_BASE_URL=$API_BASE_URL

# ── Stage 2: nginx로 정적 파일 서빙 ──
FROM nginx:1.27-alpine

# 빌드 결과물 복사
COPY --from=builder /app/build/web /usr/share/nginx/html

# SPA 라우팅을 위한 nginx 설정
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
