# RIO PRD

## 1. 문서 역할

이 문서는 RIO 프로젝트의 `기준 문서(source of truth)`입니다.

이 문서가 결정하는 범위:

- 제품 정의
- 우선 구현 기능
- 구현 기준 플랫폼
- 음성/비전/상태/스마트홈 연동 방식
- UI 레이어 구조

다른 문서와 내용이 다를 경우 이 문서를 기준으로 맞춥니다.

## 2. 제품 정의

- 제품명: `RIO`
- 제품 성격: `desktop companion robot + smart-home hub`
- 핵심 컨셉: EMO 스타일의 감정 표현과 스마트홈 허브 기능을 한 몸체에 통합한 반려형 로봇
- 핵심 가치:
  - 사용자와 눈을 맞추고 반응하는 존재감
  - 음성 명령으로 집안 기기를 제어하는 허브성
  - 사진, 타이머, 게임, 제스처 등 데스크탑 인터랙션성

## 3. 구현 기준

이 프로젝트는 아래 기준으로 구현합니다.

### 3.1 플랫폼

- 타깃 플랫폼: `Raspberry Pi` 기반 Linux
- 기준 하드웨어: `터치스크린`, `스피커`, `마이크`, `웹캠`

이 저장소에서는 Jetson과 병행 기준을 두지 않습니다.
성능 확장은 추후 고려하더라도 현재 구현 기준은 Raspberry Pi 하나입니다.
눈 방향 변화는 모터가 아니라 화면 애니메이션으로 구현합니다.
전용 터치 센서는 현재 기본 하드웨어에 포함하지 않습니다.

### 3.2 런타임

- 주 언어: `Python`
- 실행 구조:
  - `Main Orchestrator` 1개
  - `Audio Worker` 1개
  - `Vision Worker` 1개

목표는 하나의 거대한 프로그램이 아니라, 입력 인식과 행동 결정을 분리한 구조로 구현하는 것입니다.

### 3.3 기술 방향

- Vision: `OpenCV + MediaPipe`
- Speech: `오디오 캡처 + VAD + STT + Intent Normalizer`
- Smart Home: `로컬 home-client`에 HTTP 요청 전달
- UI: `로컬 3-layer renderer`
- 로직 중심축: `event-driven + state-centered`

여기서 중요한 점은 라이브러리 이름보다 `구현 계약`입니다.
예를 들어 STT 엔진은 어댑터 뒤에 감추고, 상위 계층은 항상 정규화된 텍스트와 intent만 받습니다.

## 4. 제품 목표

1. 감성 교감
   얼굴 추적, 터치스크린 상호작용, 놀람, 반김, 졸음 상태 같은 반응을 통해 로봇다운 존재감을 만든다.

2. 스마트 제어
   음성 명령으로 ThinQ 및 로컬 스마트홈 기기를 제어하고, 결과를 얼굴/사운드/UI로 피드백한다.

3. 데스크탑 인터랙션
   사진 촬영, 타이머, 날씨, 게임, 제스처 기반 놀이를 제공한다.

## 5. 우선 구현 범위

### 5.1 MVP 범위

- 얼굴 검출 및 face presence 추적
- 음성 명령 인식
- 기본 댄스 모드
- 사진 촬영
- 타이머
- 날씨 안내
- ThinQ/스마트홈 명령 전달
- 유휴 -> 졸음 -> 재등장 반응
- 터치스크린 반응
- 게임 모드 UI 전환

### 5.2 Phase 2 범위

- 손동작 기반 `빵야!`
- `참참참`
- `숨바꼭질`
- 게임 콘텐츠 확장
- 댄스 모드의 고급 연출
- 제스처 기반 촬영 트리거

이렇게 나누는 이유는, 현재 문서는 실제 구현에 바로 쓰이기 위한 문서이므로
초기 릴리즈 범위와 후속 확장 범위를 명확히 분리해야 하기 때문입니다.
아래 항목은 feature-complete 기준으로는 여전히 Phase 2 범위이며,
현재 저장소에는 일부 반응형 프로토타입이 선반영될 수 있습니다.

## 6. 명령 체계

문서마다 서로 다른 문장을 하드코딩하지 않기 위해, 음성 명령은 `intent` 기준으로 관리합니다.
실제 문구 alias는 설정 파일에서 확장합니다.

### 6.1 Canonical Intents

| Intent ID | 예시 발화 | 결과 |
| :--- | :--- | :--- |
| `dance.start` | "emo dance!", "RIO dance!", "춤춰" | 댄스 모드 시작 |
| `camera.capture` | "사진 찍어줘" | 카운트다운 후 사진 촬영 |
| `ui.game_mode.enter` | "게임 모드로 바꿔줘" | 게임 UI로 전환 |
| `timer.create` | "~분 있다 알려줘" | 타이머 생성 |
| `weather.current` | "날씨 알려줘" | 날씨 조회 후 응답 |
| `smarthome.aircon.on` | "에어컨 켜줘" | home-client 제어 요청 |
| `smarthome.aircon.off` | "에어컨 꺼줘" | home-client 제어 요청 |
| `smarthome.aircon.set_temperature` | "온도 28도로 맞춰줘" | home-client 제어 요청 |
| `smarthome.light.on` | "불 켜줘" | home-client 제어 요청 |
| `smarthome.light.off` | "불 꺼줘" | home-client 제어 요청 |
| `smarthome.robot_cleaner.start` | "로봇 청소기 실행시켜줘" | home-client 제어 요청 |
| `smarthome.tv.on` | "티비 켜줘" | home-client 제어 요청 |
| `smarthome.music.play` | "음악 틀어줘" | home-client 제어 요청 |
| `system.cancel` | "취소", "그만" | 현재 Listening/Executing 중단 |
| `system.ack` | "응", "알았어", "확인" | Alerting 해제, 확인 피드백 |

### 6.2 명령 정규화 원칙

- 문서에는 `intent`를 기준으로 적습니다.
- 실제 발화 문장 alias는 `configs/triggers.yaml`에 둡니다.
- 상위 로직은 `"사진 찍어줘"`라는 문자열이 아니라 `camera.capture` intent를 받습니다.

## 7. 입력 수단별 기능 명세

### 7.1 Voice Input

| 입력 | 처리 결과 |
| :--- | :--- |
| 댄스 명령 | 댄스 씬 시작 |
| 사진 촬영 명령 | 카운트다운 -> 셔터 -> 저장 피드백 |
| 게임 모드 명령 | 얼굴 UI 축소 및 게임용 버튼 표시 |
| 타이머 명령 | 자연어 시간 파싱 후 타이머 등록 |
| 날씨 명령 | 날씨 API 조회 후 음성/화면 응답 |
| 스마트홈 명령 | home-client에 제어 요청 전달 |

### 7.2 Voice 기반 상황 반응

| 상황 | 처리 결과 |
| :--- | :--- |
| 얼굴이 없는데 음성 감지 | `화들짝` 반응 후 face search 시작 |
| 재등장 직후 n초 안에 음성 감지 | `깜짝 + 반김` 계열 반응 |

### 7.3 Vision Input

| 입력 | 처리 결과 |
| :--- | :--- |
| 얼굴 검출 | 화면 기반 시선 추적 활성화 |
| 얼굴 중심 이동 | 눈동자/얼굴 UI 애니메이션 방향 보정 |
| 손 흔들기 | slow blink 또는 인사 반응 |
| 얼굴 장기 미검출 | 졸음/수면 상태 진입 |
| 얼굴 재등장 | 반김 이벤트 발생 |
| 손가락 총 모양 | 쓰러짐 모션 |
| 고개 좌/우 방향 | 참참참 승패 판정 |
| 얼굴 가림 후 재등장 | 숨바꼭질 이벤트 |
| V자 손동작 | 사진 촬영 트리거 |

위 표의 기능 중 `얼굴 검출`, `얼굴 중심 이동`, `장기 미검출`, `재등장`은 MVP 기준입니다.
제스처 중심 기능은 feature-complete 기준으로는 Phase 2 범위이며,
현재 저장소에는 `V자 손동작`과 일부 반응형 gesture가 프로토타입 수준으로 선반영될 수 있습니다.

### 7.4 Touchscreen / Logic Input

| 입력 | 처리 결과 |
| :--- | :--- |
| 터치스크린 탭/쓰다듬기 제스처 | 좋아하는 반응, 하트, 사운드 |
| 장시간 유휴 | 수면/꿈 애니메이션 |
| 타이머 종료 | 알람 + 얼굴/사운드 반응 |

## 8. 스마트홈 연동 기준

RIO는 스마트홈 제어를 직접 벤더 SDK에 붙이지 않고, 우선 `로컬 home-client`를 통해 제어합니다.

### 8.1 통신 계약

- Method: `PUT`
- Endpoint: 기본 `http://[HOME_CLIENT_IP]/device/control`
  - 실제 구현에서는 `configs/devices.yaml`의 `base_url + control_path` 또는 `control_url`로 구성
- Body:

```json
{
  "content": "aircon.living_room:on"
}
```

### 8.2 원칙

- 음성 명령은 먼저 intent로 정규화합니다.
- MVP 현재 구현에서는 intent를 canonical control message string으로 변환해 `content`에 담아 전송합니다.
  - 예: `aircon.living_room:on`
  - 예: `aircon.living_room:set_temperature:28`
  - 예: `light.main:off`
- 실패하더라도 RIO는 표정과 사운드로 결과를 반드시 피드백합니다.

## 9. UI 구조

RIO의 화면은 3개의 레이어로 나누어 구현합니다.
이 레이어 구조는 유지하되, 구현 프레임워크는 하나로 통일합니다.

### 9.1 구현 기준

- 기준 UI 방식: `Python 기반 로컬 renderer`
- 권장 형태: `display adapter`에서 3개 layer surface를 합성하는 방식

문서에서는 React, Tkinter, PyQt, Lottie를 병렬 기준으로 두지 않습니다.
현재 기준은 `로컬 3-layer renderer`이며, 이 구조를 코드에 그대로 반영하는 것이 목표입니다.

### 9.2 Layer 정의

- Layer 1 `Core Face`
  - 기본 표정
  - 눈 깜빡임
  - 시선 이동 애니메이션
  - 졸음/놀람/반김 기본 얼굴

- Layer 2 `Action Overlay`
  - 하트
  - 느낌표
  - 뿅망치
  - 날씨 아이콘
  - 플래시
  - 게임 오브젝트

- Layer 3 `System HUD`
  - STT 텍스트
  - 타이머 숫자
  - 상태 알림
  - 제어 결과 메시지

## 10. 상황별 연출 기준

| 상황 | Core Face | Action Overlay | System HUD | 사운드 |
| :--- | :--- | :--- | :--- | :--- |
| 평상시 | 느린 blink | 없음 | 없음 | 무음 또는 저강도 ambient |
| 음성 인식 | attentive face | listening indicator | 실시간 STT | 짧은 listening cue |
| ThinQ 제어 | 윙크 또는 미안한 표정 | 기기 아이콘 | 성공/실패 문구 | 성공/실패 beep |
| 댄스 모드 | energetic face | 배경 연출 | 선택적 상태 표시 | dance track |
| 사진 촬영 | 응시 표정 | 플래시 | 카운트다운 | 셔터음 |
| 날씨 안내 | 날씨 연동 표정 | 해/비/구름 아이콘 | 온도/강수 정보 | 브리핑 음성 |
| 화들짝 | 눈 확대 | 느낌표 | 없음 | surprised sfx |
| 수면/졸음 | half-close eyes | Zzz | 없음 | 코 고는 소리 |
| 쓰다듬기 | 웃는 얼굴 | 하트 | 없음 | 만족 사운드 |
| 게임 전환 | focus face | 게임 선택 UI | 조작 가이드 | 전환음 |

## 11. 구현 원칙

1. 입력 해석과 행동 연출은 분리합니다.
2. UI, 사운드, 네트워크 제어는 직접 서로 호출하지 않고 액션 플래너를 통해 조합합니다.
3. 상태는 하나의 거대한 FSM으로 만들지 않고 두 개의 독립 축(`Context`, `Activity`)으로 나누며, 표정과 UI는 상태가 아닌 파생 출력으로 둡니다. 상세는 [state-machine.md](state-machine.md) 참고.
4. 시간 임계치와 명령 alias는 코드가 아니라 설정 파일에서 관리합니다.
5. 네트워크 실패 시에도 로컬 인터랙션은 멈추지 않아야 합니다.

## 12. 구현 우선순위

1. 이벤트 모델 정의
2. 상태 저장소와 상태 머신
3. 얼굴 존재/부재 추적
4. 음성 명령 -> intent 정규화
5. 사진/타이머/날씨/스마트홈 서비스
6. 3-layer UI와 반응 씬
7. 제스처, 게임 확장
