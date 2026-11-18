#!/usr/bin/env bash
# bubblewrap-yuno 설치/갱신: 플러그인 복사 → 활성화.
# terminal.backend는 건드리지 않는다(켠 상태에서 ~/.hermes가 사라져 복구가 어려움).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
name="bubblewrap-yuno"
hermes_home="${HERMES_HOME:-$HOME/.hermes}"
dest="$hermes_home/plugins/$name"

command -v hermes >/dev/null || { echo "hermes CLI를 찾을 수 없습니다." >&2; exit 1; }

echo "== 1/2 플러그인 설치: $dest"
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

echo "== 2/2 활성화"
hermes plugins enable "$name"

cat <<'EOF'

완료. 백엔드 선택은 직접:
  hermes config set terminal.backend bubblewrap-yuno
되돌리기:
  hermes config set terminal.backend local

장치·경로 허용 및 리소스 제한 설정은 README.md 참고.
EOF
