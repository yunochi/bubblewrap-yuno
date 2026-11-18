# bubblewrap-yuno

Hermes Agent의 bubblewrap 터미널 샌드박스 **로컬 포크**. 임베디드 보드(ESP32 등)를
샌드박스 안에서 바로 다루기 위한 최소 수정 + 운영자 경로 신뢰 옵션을 담고 있다.

기반: `NousResearch/hermes-official-plugins` → `bubblewrap` v1.5.1 (MIT),
pin `e7a218f26db88426ab3e7376f0e000b6e356f5e7`. 업스트림 README는
[`UPSTREAM-README.md`](UPSTREAM-README.md), 차이 전문은 [`patches/`](patches/)에 있다.

## 공식 플러그인과 다른 점

| # | 변경 | 이유 |
|---|---|---|
| 1 | 장치 노드 바인드는 `--dev-bind` (`readonly: true`면 거부) | `--bind`는 마운트에 `nodev`를 남기고, 커널이 nodev 마운트의 장치 노드 open을 `EACCES`로 거부한다. `/dev/ttyACM0`이 0666으로 보이는데도 열리지 않던 원인 |
| 2 | `auto_bind_globs` + `auto_bind_globs_type` (기본: 빈 목록) | 스폰 시점에 지정한 글롭이 매칭하는 경로를 read-write로 자동 바인드. **목록 자체가 스위치**라 기본값은 "아무것도 안 함". `type: any`(기본)면 매칭된 것 전부(장치·파일·소켓·디렉터리), `device`면 문자/블록 장치 노드만. 이미 `binds`에 있는 경로는 중복되지 않는다 |
| 3 | `trust_operator` (기본 false) | 켜면 `binds`/`home_allow`에 적은 경로가 숨김 집합을 이긴다. 공식 플러그인은 `~/.hermes`, `.ssh` 등을 설정해도 조용히 무시한다 |
| 4 | 숨김용 빈 파일을 per-user 런타임 디렉터리로 이동 | 기존 `<state_dir>.empty`는 `HERMES_HOME` 옆이라, 그 디렉터리가 쓰기 가능해지면(=`trust_operator` + `~/.hermes` 바인드) 샌드박스 안 명령이 빈 파일을 시크릿 심링크로 바꿔치기할 수 있었다 |

## 요구 사항

- Linux, `bwrap`(bubblewrap) + `prlimit`
- Hermes Agent `>= 0.22.6`

## 설치

### 이 레포를 클론해서

```bash
git clone <이 레포 URL> ~/src/bubblewrap-yuno
~/src/bubblewrap-yuno/install.sh
hermes config set terminal.backend bubblewrap-yuno     # 실제로 켜기
```

`install.sh`는 플러그인 디렉터리를 `$HERMES_HOME/plugins/bubblewrap-yuno`로 복사하고
`hermes plugins enable bubblewrap-yuno`로 활성화만 한다. 신규 설치와 재설치 모두 장치·경로 규칙이나 리소스 제한을 설정하거나 지우지 않는다.
`terminal.backend`는 **일부러 건드리지 않는다** — 켜는 순간 `~/.hermes`가 샌드박스에서
사라져서, 설정이 잘못됐을 때 CLI로 되돌리기 어려워지기 때문.

### Hermes 플러그인 설치 명령으로

```bash
hermes plugins install <owner>/<repo>
hermes plugins enable bubblewrap-yuno
```

## 설정

`config.yaml`은 에이전트가 직접 쓸 수 없으니 항상 CLI로:

```bash
S=plugins.entries.bubblewrap-yuno.settings
hermes config set $S.profile network          # restricted | workspace | network
hermes config set $S.auto_bind_globs '["/dev/ttyACM*","/dev/ttyUSB*","/dev/bus/usb/*/*"]'
hermes config set $S.auto_bind_globs_type any      # any(기본) | device
# by-id 심링크는 노드로 해석되므로, 노드를 바인드하면 도구가 여는 경로는 확보된다
# (`/dev/serial/by-id/...` 경로 자체는 샌드박스의 새 /dev에 부모가 없어 바인드하지 않는다)
hermes config set $S.trust_operator false     # 필요할 때만 true

# 경로는 각자 환경에 맞게 (여기서는 홈 아래 work, ~/.espressif)
hermes config set $S.binds "[{\"src\":\"$HOME/work\",\"readonly\":false},{\"src\":\"$HOME/.espressif\",\"readonly\":true}]"
hermes config set $S.home_allow '[".ssh"]'    # trust_operator=true일 때만 의미 있음
```

재설치는 기존 `binds`를 보존한다. 예전 설정이라면 다른 항목은 유지하고 `~/.espressif` 항목만 `readonly: true`로 바꾼다. 장치 자체를 제어하면 안 되는 작업에서는 해당 장치 바인드와 자동 매칭을 빼야 한다.

`~/.espressif` 같은 경로를 바인드하면 IDF 툴체인(`tools/python/v6.1/venv/bin/esptool`,
`v6.1/esp-idf`)을 샌드박스 안에서 그대로 쓸 수 있다.

### 선택: 빌드용 리소스 제한 해제

기본 제한을 유지하려면 아무 설정도 하지 않는다. 기존 설치에서 값을 `0`으로 지정했다면 재설치해도 그대로다. 제한 해제가 필요한 항목만 선택해서 실행한다.

```bash
S=plugins.entries.bubblewrap-yuno.settings
hermes config set $S.memory_mb 0              # 0 = 제한 없음
hermes config set $S.cpu_seconds 0
hermes config set $S.max_procs 0
```

## 확인

```bash
python3 -c "import os; fd=os.open('/dev/ttyACM0', os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); print('ok', os.isatty(fd))"
awk '$5=="/dev/ttyACM0"' /proc/self/mountinfo      # rw,nosuid  (nodev가 없어야 정상)
esptool version                                    # ~/.espressif 바인드 시
```

보드에 실제로 접근하는 확인(`esptool chip-id`, `idf.py monitor`)은 DTR/RTS를 건드려
**대상을 리셋**한다. 다른 모니터가 열려 있으면 먼저 확인할 것.

## 보안 경고 — `trust_operator`

켜면 `binds`/`home_allow`에 적은 경로가 숨김 규칙을 이긴다. 특히 `~/.hermes`를
read-write로 바인드하면 샌드박스 안 명령이 **이 플러그인 코드와 `config.yaml`을 고칠 수
있고**, 그 수정은 다음 스폰에서 호스트 권한으로 실행된다. 즉 샌드박스 경계 하나를
없애는 것과 같다. 기본값은 `false`이고, 필요할 때만 켠다.

**swap 검사는 신뢰 모드에서도 그대로 적용된다.** 바인드 소스가 샌드박스가 쓸 수 있는
디렉터리(cwd 등) 안에 있으면, 안의 명령이 심링크 하나로 다음 스폰의 마운트 소스를
바꿔치기해 예상 밖 경로(숨김 파일, `/dev/nvme0n1` 같은 장치)를 얻을 수 있기 때문이다.
수동 `binds`는 스폰을 실패시키고(설정 오류), 자동 바인드는 그 항목만 경고 후 건너뛴다.
예외는 백엔드 자신의 경로(`$TMPDIR`용 스크래치, 프로필 홈)뿐이고, 그건 이미 신뢰된
트리 안이라 바꿔치기로 얻을 게 없기 때문이다.

숨김용 빈 파일이 사는 `~/.hermes`가 아닌 `/run/user/<uid>/hermes-bwrap-empty`를
read-write로 바인드하면 같은 이유로 **생성 시점에 거부**한다(파일 이름이 스폰마다
랜덤이고 마운트 직전에 만들어져 실질 위험은 낮지만, 타이밍 운에 기대지 않는다).
read-only 바인드는 빈 파일만 보이므로 허용된다.

## 업스트림 동기화

```bash
# 차이 확인
diff -ru --exclude=__pycache__ --exclude='*.patch' \
    ~/.hermes/plugins/bubblewrap ~/.hermes/plugins/bubblewrap-yuno

# 업스트림이 새 버전이면: 새 공식 플러그인을 기준으로 위 diff를 다시 얹고
# patches/0001-hardware-fork.patch를 갱신, plugin.yaml의 +yuno.N을 올린다
```

## 파일

- `sandbox.py` — 샌드박스 argv 생성 (변경 1·2·4의 본체, `trust_operator` 배선)
- `binds.py` — 바인드 검증 가드 (`BindGuard.trust_operator`)
- `home.py` — HOME 레이아웃/허용목록 (설정 키 이름만 포크 것으로)
- `__init__.py` — 백엔드 provider 등록, 프롬프트 노트
- `tests/` — 업스트림 테스트 (이 환경의 venv에는 pytest가 없어 기본 실행 불가)

## 주의: `.hermes-catalog.json`

포크 디렉터리에 이 파일을 두지 않는다. 공식 카탈로그 출처(`NousResearch/hermes-official-plugins`)가
적힌 파일이라 `hermes plugins update`가 업스트림으로 덮어쓸 수 있다. 이 레포에는 없고,
`install.sh`도 복사한 뒤 지운다.
