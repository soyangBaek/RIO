# RIO

RIO는 Raspberry Pi 위에서 동작하는 `desktop pet + smart-home hub` 프로젝트입니다.
이 저장소의 문서는 `감정형 반응`, `음성/비전 인터랙션`, `ThinQ 연동`을 하나의 구현 방향으로 맞추는 것을 목표로 합니다.

## 문서 기준

`[docs/prd.md](./docs/prd.md)`가 이 프로젝트의 기준 문서입니다.

- 기능 범위
- 구현 기준
- 명령 의도 체계
- 우선 구현 순서

위 항목에서 다른 문서와 충돌이 생기면 `prd.md`를 우선합니다.
`architecture.md`, `state-machine.md`, `project-layout.md`는 모두 `prd.md`를 구현 가능한 형태로 풀어쓴 파생 문서입니다.

## 고정된 구현 방향

이 저장소는 아래 기준으로 통일합니다.

- 플랫폼: `Raspberry Pi` 기반 Linux
- 하드웨어: `터치스크린`, `스피커`, `마이크`, `웹캠`
- 주 언어: `Python`
- 실행 구조: `main orchestrator + audio worker + vision worker`
- 핵심 방식: `event-driven + state-centered`
- 비전: `OpenCV + MediaPipe`
- 스마트홈 연동: `로컬 home-client`로 HTTP 요청 전달
- 화면: `로컬 3-layer face UI`

의도적으로 제외한 것:

- Jetson과 Raspberry Pi를 동시에 기준 플랫폼으로 두는 문서화
- React, Tkinter, PyQt 등 여러 UI 프레임워크를 동시에 기준으로 두는 문서화
- 명령어 문자열을 문서마다 다르게 하드코딩하는 방식
- 눈 방향 변화를 모터 제어로 전제하는 문서화
- 전용 터치 센서를 현재 기본 하드웨어처럼 전제하는 문서화

## 문서 목록

- [PRD / 기준 문서](./docs/prd.md)
- [Current Behaviors](./docs/current-behaviors.md)
- [Architecture](./docs/architecture.md)
- [State Machine](./docs/state-machine.md)
- [Scenario Catalog](./docs/scenarios.md)
- [Project Layout](./docs/project-layout.md)

## 현재 상태

기본 구조와 입력/반응 플로우는 구현되어 있으며, `scripts/live_interaction_test.py`로 현재 동작을 직접 검증할 수 있습니다.
실행 가능한 입력과 현재 반응은 [docs/current-behaviors.md](./docs/current-behaviors.md)에 정리되어 있습니다.

## 실행

기본 음성 런타임은 `configs/voice.yaml` 기준으로 `RustAudioBackend`를 우선 사용합니다.
스크립트를 실행하면 Python 쪽이 Rust worker를 자동으로 subprocess로 띄우므로, 평소에는 worker를 따로 먼저 실행할 필요가 없습니다.
Rust worker 기동에 실패하면 현재 설정에서는 Python live voice backend로 자동 fallback 됩니다.

자주 쓰는 실행 예:

- `PYTHONPATH=. .venv/bin/python scripts/run_rio_app.py --profile app`


실행 시 아래 로그가 보이면 Rust 경로가 올라온 상태입니다.

- `[voice] starting live mic backend (RustAudioBackend)...`
- `voice_sandbox`에서는 heartbeat에 `backend=RUST` 표시

## Rust Audio Worker

Rust audio worker 소스는 [native/rio-audio-worker](./native/rio-audio-worker)에 있고, 기본 실행 바이너리는 [native/bin/rio-audio-worker](./native/bin/rio-audio-worker) 입니다.
`configs/voice.yaml`의 `backend.worker_path` 기본값도 이 바이너리를 가리킵니다.

일반 실행만 할 때는 Rust 툴체인이 없어도 됩니다.
바이너리를 다시 빌드하거나 갱신할 때만 툴체인이 필요합니다.

바이너리 갱신 절차:

```bash
cd native/rio-audio-worker
cargo build --release
cd ../..
mkdir -p native/bin
install -m 755 native/rio-audio-worker/target/release/rio-audio-worker native/bin/rio-audio-worker
```

즉 `target/` 전체를 커밋하지 않고, 실행에 쓰는 바이너리만 `native/bin/`에 복사해서 추적하는 방식을 사용합니다.
