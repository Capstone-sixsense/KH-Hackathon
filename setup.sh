#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  khuthon 2026 – Docker 환경 자동 셋업 스크립트
#  사용법: chmod +x setup.sh && ./setup.sh
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── 색상 정의 ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── 출력 헬퍼 ────────────────────────────────────────────────
info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()    { echo -e "\n${BOLD}${CYAN}▶ $*${RESET}"; }
divider() { echo -e "${CYAN}────────────────────────────────────────────────────────${RESET}"; }

# ── 스크립트 위치 기준으로 작업 디렉토리 고정 ─────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ════════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}${CYAN}  khuthon 2026 · 환경 자동 셋업${RESET}"
divider

# ════════════════════════════════════════════════════════════════
# STEP 1 · 필수 도구 확인
# ════════════════════════════════════════════════════════════════
step "필수 도구 확인"

check_command() {
  local cmd=$1
  local install_hint=$2
  if command -v "$cmd" &>/dev/null; then
    success "$cmd $(${cmd} --version 2>&1 | head -1)"
  else
    error "$cmd 가 설치되어 있지 않습니다."
    echo  "       설치 방법: $install_hint"
    exit 1
  fi
}

check_command docker    "https://docs.docker.com/get-docker/"
check_command git       "https://git-scm.com/downloads"

# docker compose v2 (plugin) 또는 v1 (standalone) 확인
if docker compose version &>/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
  success "docker compose $(docker compose version --short)"
elif command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
  success "docker-compose $(docker-compose --version)"
else
  error "docker compose 플러그인이 없습니다. Docker Desktop 또는 compose plugin을 설치해주세요."
  exit 1
fi

# Docker 데몬 실행 확인
if ! docker info &>/dev/null; then
  error "Docker 데몬이 실행 중이지 않습니다. Docker를 먼저 실행해주세요."
  exit 1
fi
success "Docker 데몬 정상 실행 중"

# ════════════════════════════════════════════════════════════════
# STEP 2 · 필수 파일/폴더 구조 확인
# ════════════════════════════════════════════════════════════════
step "프로젝트 구조 확인"

REQUIRED_DIRS=("backend" "frontend")
REQUIRED_FILES=("docker-compose.yml" "backend/Dockerfile" "frontend/Dockerfile" "frontend/nginx.conf")

for dir in "${REQUIRED_DIRS[@]}"; do
  if [ ! -d "$dir" ]; then
    warn "'$dir' 폴더가 없어 생성합니다."
    mkdir -p "$dir"
  else
    success "'$dir' 폴더 확인"
  fi
done

for file in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$file" ]; then
    error "필수 파일 '$file' 이 없습니다. 파일을 먼저 추가해주세요."
    exit 1
  else
    success "'$file' 확인"
  fi
done

# ════════════════════════════════════════════════════════════════
# STEP 3 · Flutter 프로젝트 초기화 (pubspec.yaml 없을 때)
# ════════════════════════════════════════════════════════════════
step "Flutter 프로젝트 확인"

if [ -f "frontend/pubspec.yaml" ]; then
  success "Flutter 프로젝트 확인 (pubspec.yaml 존재)"
else
  warn "frontend/pubspec.yaml 이 없습니다. Flutter 프로젝트를 초기화합니다."
  info "Docker로 Flutter 이미지를 pull하여 프로젝트를 생성합니다 (첫 실행 시 시간이 걸립니다)..."

  docker run --rm \
    -v "$SCRIPT_DIR/frontend:/app" \
    -w /app \
    ghcr.io/cirruslabs/flutter:stable \
    flutter create . \
      --project-name khuthon \
      --org com.khuthon \
      --platforms web \
      --no-overwrite

  success "Flutter 프로젝트 초기화 완료"
  info "frontend/ 폴더에 기본 프로젝트가 생성되었습니다."
fi

# ════════════════════════════════════════════════════════════════
# STEP 4 · 환경변수(.env) 설정
# ════════════════════════════════════════════════════════════════
step "환경변수(.env) 설정"  # STEP 4

if [ -f ".env" ]; then
  warn ".env 파일이 이미 존재합니다. 덮어쓰지 않습니다."
else
  if [ -f ".env.example" ]; then
    cp .env.example .env
    info ".env.example → .env 복사 완료"
  else
    # .env.example이 없으면 기본 템플릿 생성
    cat > .env << 'EOF'
# Spotify API  →  https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=

# Last.fm API  →  https://www.last.fm/api/account/create
LASTFM_API_KEY=
LASTFM_API_SECRET=
EOF
    info ".env 기본 템플릿 생성 완료"
  fi
fi

# API 키 입력 여부 확인
source .env 2>/dev/null || true

MISSING_KEYS=()
[ -z "${SPOTIFY_CLIENT_ID:-}"     ] && MISSING_KEYS+=("SPOTIFY_CLIENT_ID")
[ -z "${SPOTIFY_CLIENT_SECRET:-}" ] && MISSING_KEYS+=("SPOTIFY_CLIENT_SECRET")
[ -z "${LASTFM_API_KEY:-}"        ] && MISSING_KEYS+=("LASTFM_API_KEY")
[ -z "${LASTFM_API_SECRET:-}"     ] && MISSING_KEYS+=("LASTFM_API_SECRET")

if [ ${#MISSING_KEYS[@]} -gt 0 ]; then
  echo ""
  warn "아직 채워지지 않은 API 키가 있습니다:"
  for key in "${MISSING_KEYS[@]}"; do
    echo -e "  ${YELLOW}·${RESET} $key"
  done
  echo ""

  # 대화형 터미널일 경우 직접 입력 안내
  if [ -t 0 ]; then
    read -r -p "$(echo -e "${BOLD}지금 바로 입력하시겠습니까? [y/N]: ${RESET}")" ANSWER
    if [[ "${ANSWER,,}" == "y" ]]; then
      for key in "${MISSING_KEYS[@]}"; do
        read -r -p "  $key = " val
        # macOS(BSD sed)와 Linux(GNU sed) 모두 대응
        if [[ "$OSTYPE" == "darwin"* ]]; then
          sed -i '' "s|^${key}=.*|${key}=${val}|" .env
        else
          sed -i "s|^${key}=.*|${key}=${val}|" .env
        fi
      done
      success "API 키 저장 완료"
    else
      warn ".env 파일에 직접 입력한 뒤 './setup.sh' 을 다시 실행하거나,"
      warn "'$COMPOSE_CMD up --build' 를 실행해주세요."
      echo ""
    fi
  fi
else
  success "모든 API 키 확인 완료"
fi

# ════════════════════════════════════════════════════════════════
# STEP 5 · 기존 컨테이너 정리 (선택)
# ════════════════════════════════════════════════════════════════
step "기존 컨테이너 정리"

EXISTING=$($COMPOSE_CMD ps -q 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  warn "이미 실행 중인 컨테이너가 감지되었습니다."
  if [ -t 0 ]; then
    read -r -p "$(echo -e "${BOLD}기존 컨테이너를 내리고 다시 빌드할까요? [y/N]: ${RESET}")" ANSWER
    if [[ "${ANSWER,,}" == "y" ]]; then
      $COMPOSE_CMD down --remove-orphans
      success "기존 컨테이너 종료 완료"
    else
      info "기존 컨테이너를 유지합니다."
    fi
  else
    $COMPOSE_CMD down --remove-orphans
    success "기존 컨테이너 종료 완료 (비대화형 모드)"
  fi
else
  info "실행 중인 컨테이너 없음"
fi

# ════════════════════════════════════════════════════════════════
# STEP 6 · Docker 이미지 빌드
# ════════════════════════════════════════════════════════════════
step "Docker 이미지 빌드 (시간이 걸릴 수 있습니다…)"

$COMPOSE_CMD build --parallel
success "이미지 빌드 완료"

# ════════════════════════════════════════════════════════════════
# STEP 7 · 컨테이너 실행
# ════════════════════════════════════════════════════════════════
step "컨테이너 실행"

$COMPOSE_CMD up -d
success "모든 컨테이너 백그라운드 실행 완료"

# ════════════════════════════════════════════════════════════════
# STEP 8 · 서비스 헬스체크
# ════════════════════════════════════════════════════════════════
step "서비스 헬스체크"

info "서비스가 준비될 때까지 대기 중..."
sleep 5

MAX_RETRY=12   # 최대 60초 대기
RETRY_INTERVAL=5

backend_ready=false
for i in $(seq 1 $MAX_RETRY); do
  if curl -sf http://localhost:8000/health &>/dev/null; then
    success "Backend (FastAPI) 응답 확인 ✓"
    backend_ready=true
    break
  fi
  info "Backend 응답 대기 중... (${i}/${MAX_RETRY})"
  sleep $RETRY_INTERVAL
done

if [ "$backend_ready" = false ]; then
  warn "Backend 헬스체크 응답이 없습니다."
  warn "'/health' 엔드포인트가 구현되어 있는지 확인해주세요."
fi

if curl -sf http://localhost:3000 &>/dev/null; then
  success "Frontend (Flutter Web) 응답 확인 ✓"
else
  warn "Frontend 응답이 없습니다. Flutter 빌드가 완료되지 않았을 수 있습니다."
fi

# ════════════════════════════════════════════════════════════════
# 완료 안내
# ════════════════════════════════════════════════════════════════
echo ""
divider
echo -e "${BOLD}${GREEN}  ✅  셋업 완료!${RESET}"
divider
echo -e "  ${BOLD}Frontend${RESET}   →  http://localhost:3000"
echo -e "  ${BOLD}Backend${RESET}    →  http://localhost:8000"
echo -e "  ${BOLD}API Docs${RESET}   →  http://localhost:8000/docs  (Swagger UI)"
echo -e "  ${BOLD}Redis${RESET}      →  localhost:6379"
echo ""
echo -e "  ${BOLD}유용한 명령어${RESET}"
echo -e "  ${CYAN}$COMPOSE_CMD logs -f${RESET}               # 전체 로그 스트림"
echo -e "  ${CYAN}$COMPOSE_CMD logs -f backend${RESET}       # 백엔드 로그만"
echo -e "  ${CYAN}$COMPOSE_CMD down${RESET}                  # 전체 종료"
echo -e "  ${CYAN}$COMPOSE_CMD restart backend${RESET}       # 백엔드만 재시작"
divider