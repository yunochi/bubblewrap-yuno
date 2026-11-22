#!/usr/bin/env bash
# bubblewrap-yuno 설치/갱신: 플러그인 복사 → 활성화 → 기본 설정 적용.
# terminal.backend는 건드리지 않는다(켠 상태에서 ~/.hermes가 사라져 복구가 어려움).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
name="bubblewrap-yuno"
hermes_home="${HERMES_HOME:-$HOME/.hermes}"
dest="$hermes_home/plugins/$name"

command -v hermes >/dev/null || { echo "hermes CLI를 찾을 수 없습니다." >&2; exit 1; }

echo "== 1/3 플러그인 설치: $dest"
mkdir -p "$(dirname "$dest")"
if [ "$(cd "$here" && pwd -P)" != "$(cd "$dest" 2>/dev/null && pwd -P || echo "")" ]; then
    rm -rf "$dest"
    cp -a "$here" "$dest"
    rm -rf "$dest/.git" "$dest/__pycache__" "$dest/tests/__pycache__"
    # 업스트림 카탈로그 표식: 있으면 plugins update가 이 포크를 덮어쓴다
    rm -f "$dest/.hermes-catalog.json"
else
    echo "   (이미 목적지에서 실행 중: 복사 생략)"
fi

echo "== 2/3 활성화"
hermes plugins enable "$name" || true

echo "== 3/3 기본 설정"
set_cfg() { hermes config set "plugins.entries.$name.settings.$1" "$2"; }
get_cfg() { hermes config get "plugins.entries.$name.settings.$1" 2>&1; }
# 이미 값이 있으면 건드리지 않는다(재설치가 운영자 설정을 덮어쓰지 않도록).
set_cfg_if_unset() {
    local key="$1" value="$2" out first
    out="$(get_cfg "$key")"
    if [ -z "$out" ] || printf '%s' "$out" | grep -q '^Config key not set'; then
        set_cfg "$key" "$value"
    else
        first="$(printf '%s\n' "$out" | head -1)"
        echo "   $key 유지: $first"
    fi
}

set_cfg_if_unset auto_bind_globs '["/dev/ttyACM*","/dev/ttyUSB*"]'
set_cfg_if_unset auto_bind_globs_type any
set_cfg_if_unset trust_operator false
set_cfg_if_unset memory_mb 0
set_cfg_if_unset cpu_seconds 0
set_cfg_if_unset max_procs 0
# 샌드박스에 넣을 추가 경로. 필요 없다면 SANDBOX_DIRS="" 로 두세요.
# 기본값은 작업 디렉터리와 ESP-IDF 도구 디렉터리.
SANDBOX_DIRS="${SANDBOX_DIRS-[$HOME/work,$HOME/.espressif]}"
if [ -n "$SANDBOX_DIRS" ]; then
    binds_json="$(printf '%s' "$SANDBOX_DIRS" | python3 -c '
import json,sys
raw = sys.stdin.read().strip().strip("[]")
dirs = [d.strip() for d in raw.split(",") if d.strip()]
print(json.dumps([{"src": d, "readonly": False} for d in dirs]))
')"
    set_cfg_if_unset binds "$binds_json"
fi

cat <<'EOF'

완료. 백엔드 선택은 직접:
  hermes config set terminal.backend bubblewrap-yuno
되돌리기:
  hermes config set terminal.backend local

확인:
  python3 -c "import os; fd=os.open('/dev/ttyACM0', os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); print('ok', os.isatty(fd))"
EOF
