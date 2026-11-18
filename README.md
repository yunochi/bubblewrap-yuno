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
| 2 | `auto_bind_globs` + `auto_bind_globs_type` (기본: 빈 목록) | 명령을 시작할 때마다 글롭에 일치하는 경로를 찾아 안전한 매치만 read-write로 바인드한다. **목록 자체가 스위치**라 기본값은 "아무것도 안 함". `type: any`(기본)면 매칭된 것 전부(장치·파일·소켓·디렉터리), `device`면 문자/블록 장치 노드만. 이미 `binds`에 있는 경로는 중복되지 않는다 |
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
```

`install.sh`는 플러그인 디렉터리를 `$HERMES_HOME/plugins/bubblewrap-yuno`로 복사하고
`hermes plugins enable bubblewrap-yuno`로 활성화만 한다. 신규 설치와 재설치 모두 장치·경로 규칙이나 리소스 제한을 설정하거나 지우지 않는다.

### Hermes 플러그인 설치 명령으로

```bash
hermes plugins install <owner>/<repo>
hermes plugins enable bubblewrap-yuno
```

## 설정

아래는 `$HERMES_HOME/config.yaml`에 넣을 펌웨어 개발용 예시다. 기존 `terminal`과 `plugins.entries`에 필요한 항목만 합친다. `/home/user/work` 두 곳은 미리 만든 작업 폴더의 절대 경로로 바꾼다.

```yaml
terminal:
  backend: bubblewrap-yuno
  cwd: /home/user/work

plugins:
  entries:
    bubblewrap-yuno:
      settings:
        profile: network
        trust_operator: true
        home_allow: [".espressif", ".hermes"]
        binds:
          - src: /home/user/work
            readonly: false
        auto_bind_globs_type: device
        auto_bind_globs: ["/dev/ttyACM*", "/dev/ttyUSB*"]

        # 펌웨어 빌드용 예시: 0은 해당 제한을 해제한다.
        memory_mb: 0
        cpu_seconds: 0
        max_procs: 0
```

### 작업 디렉터리와 쓰기 범위

`terminal.cwd`는 프로젝트를 지정하지 않은 채팅의 기본 작업 폴더다. `.`은 대화의 프로젝트가 아니라 Hermes 프로세스의 현재 위치를 뜻하므로, 게이트웨이 실행 위치에 따라 홈이 쓰기 범위가 될 수 있다.

코딩 세션은 프로젝트 폴더에서 `hermes --tui --in .` 또는 `hermes --cli --in .`으로 시작한다. `workspace`와 `network` 프로필에서는 선택한 프로젝트가 쓰기 가능한 작업 폴더다. 세션 안에서 `cd`해도 쓰기 권한은 바뀌지 않는다. 예시의 `binds`는 프로젝트를 옮겨도 공용 스크래치인 `~/work`를 계속 쓸 수 있게 한다.

### 홈 항목과 추가 바인드

| 설정 | 용도 |
|---|---|
| `home_allow` | 샌드박스 홈에 원래 이름으로 보여 줄 항목. `.espressif` 같은 최상위 숨김 디렉터리나 `.config/nvim` 같은 허용 단위를 읽기 전용으로 노출한다. |
| `binds` | 특정 파일·디렉터리·장치를 직접 마운트한다. `src`는 호스트 경로, `dest`는 샌드박스 경로(생략 시 `src`), `readonly`는 생략 시 `true`다. |
| `trust_operator` | `true` 로 설정할 경우 업스트림 플러그인의  `~/.hermes`, `.ssh` 등을 설정해도 무시하는 동작을 비활성화 한다. |


- `trust_operator: true`로 상위 경로를 허용하면 하위 경로를 `hide`에 넣어도 숨겨지지 않는다.
- 상위 디렉터리가 RO여도 `$TMPDIR`처럼 별도로 RW 마운트한 하위 경로에는 쓸 수 있다.

### 장치 허용


자동 목록은 기본적으로 비어 있다. 일치하는 장치는 RW로 바인드한다. `device`는 문자·블록 장치만 받지만 기본 타입 `any`는 파일·소켓·디렉터리도 받는다. `/dev/bus/usb/*/*`는 시리얼 포트에 한정되지 않으므로 직접 USB 접근이 필요할 때만 추가한다. 글롭으로 발견한 경로는 `trust_operator`를 켜도 숨김 목록을 바꾸지 않는다. 디렉터리는 하위 트리 전체를 쓰기 가능하게 하므로 기존 마운트·쓰기 범위·보호 경로와 겹치거나 HOME 도트 심링크의 대상을 포함하면 건너뛴다.

장치 하나만 허용하려면 글롭 대신 `binds` 목록에 `{"src":"/dev/ttyACM0","readonly":false}`를 추가한다. 문자·블록 장치에서는 `readonly: true`와 생략 모두 오류다. 파일시스템을 RO로 마운트해도 장치 제어까지 막을 수 없기 때문이다.


## 확인

```bash
pwd -P
findmnt -T . -o TARGET,VFS-OPTIONS
findmnt -T "$HOME/.espressif" -o TARGET,VFS-OPTIONS
findmnt -M /dev/ttyACM0 -o TARGET,VFS-OPTIONS   # 장치를 허용했다면 rw, nodev 없음
```

패턴 설정 자체를 바꾸면 새 터미널 환경이 필요하다. 이미 설정한 `/dev/ttyACM*`에 해당하는 장치가 `ttyACM0`에서 `ttyACM1`로 바뀌면 같은 세션의 **다음 명령**이 새 경로를 잡는다. 이미 실행 중인 시리얼 모니터는 새 포트에 다시 연결해야 한다.

## 보안 경고

**Unix 소켓을 `readonly: true`로 바인드해도 소켓으로 보내는 요청은 읽기 전용이 되지 않는다.** 샌드박스에서 소켓에 연결할 수 있다면 어떤 작업을 요청할 수 있는지는 마운트 옵션이 아니라 그 서비스를 제공하는 쪽의 권한 정책이 결정한다. 예를 들어 root로 동작하는 Docker 데몬의 소켓(`/var/run/docker.sock`)에 제한 없이 접근할 수 있으면 사실상 호스트 관리자 권한을 얻는다. 소켓을 바인드할 때는 해당 서비스의 제어 권한까지 허용하려는 것인지 확인한다.

`trust_operator: true`이면 `binds`/`home_allow`에 적은 경로가 숨김 규칙을 이긴다. 특히 `~/.hermes`를
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
