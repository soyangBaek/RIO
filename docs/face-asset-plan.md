# Face Asset Plan

Figma 30개 Rosto 표정을 RIO 상태 머신의 Mood/UI/Oneshot에 매핑하고,
런타임에 필요한 에셋 목록과 애니메이션 구현 전략을 정리한 문서입니다.

> 기준 문서: `state-machine.md §6`, `architecture.md §6`, `project-layout.md §4`
> Figma 원본: `assets/figma_reference/rosto-01.png ~ rosto-30.png` (2560x1440, 2x scale)

---

## 1. Figma Rosto → RIO Mood/State 매핑

### 1.1 Primary Mapping (필수 — 상태 머신에서 직접 사용)

| RIO Mood/State | Rosto # | 설명 | 용도 |
|---|---|---|---|
| **calm** (기본 idle) | 02 | 세로선 눈, 작은 미소 | Context=Idle, Activity=Idle |
| **attentive** | 22 | 안경형 사각 눈, 일자 입 | Listening, Executing 고정 표정 |
| **sleepy** | 10 | 반감긴 눈, 작은 입 | Context=Sleepy |
| **alert** | 29 | 화난 각진 눈, 찡그린 입 | Activity=Alerting (타이머 등) |
| **sleepy (dim)** | 10 (dimmed) | sleepy와 동일, 밝기 30% | Context=Away, Activity=Idle |
| **startled** (oneshot) | 03 | 동그란 O 눈, O 입 | 얼굴 없이 큰 소리, 급재등장 |
| **confused** (oneshot) | 14 | 소용돌이 눈, 물결 입 | intent 해석 실패 |
| **welcome** (oneshot) | 04 | 별/반짝 눈, 활짝 웃음 | just_reappeared |
| **happy** (oneshot) | 24 | 위로 휜 초승달 눈, 활짝 웃음 | 쓰다듬기, 성공 피드백 |

### 1.2 Secondary Mapping (Executing(kind) 및 특수 장면)

| 장면 / kind | Rosto # | 설명 | 용도 |
|---|---|---|---|
| Executing(photo) 카운트다운 | 23 | 동그란 눈, 웃는 입 | 사진 촬영 시퀀스 |
| Executing(photo) 셔터 | 18 | 한쪽 눈 감은 윙크 | 촬영 완료 순간 |
| Executing(game) | 06 | 점 눈, 픽셀 패턴 입 | 게임 모드 전용 |
| Executing(dance) | 07 | 가늘게 웃는 눈, 물결 입 | 댄스 모드 |
| Executing(smarthome) 성공 | 18 | 윙크 | smarthome 성공 피드백 |
| Executing(smarthome) 실패 | 16 | 슬픈 눈, 울상 입 | smarthome 실패 피드백 |
| Executing(weather) | 25 | 큰 원형 눈, 디테일 입 | 날씨 조회 중 |
| petting reaction | 12 | 하트 눈, 미소 | 터치 쓰다듬기 반응 |
| KO/defeated (게임 패배) | 11 | X 눈, 꺾인 입 | 게임 결과 |

### 1.3 Reserve Pool (확장/변형용)

| Rosto # | 표정 설명 | 잠재 용도 |
|---|---|---|
| 01 | 혀 내민 행복, 볼 터치 | petting 대안, 특수 happy 변형 |
| 05 | 큰 눈, 혀 내밀기 | 장난스러운 반응 |
| 08 | 다이아 눈, 일자 입 | 로봇 모드/부팅 |
| 09 | ><  찡그린 눈, 곡선 입 | 장난꾸러기 |
| 13 | 큰 눈, 넓은 사각 입 | startled 대안 (놀람 강도 높음) |
| 15 | 점 눈, 이빨 드러난 입 | 화남/외침 |
| 17 | 옆 보는 눈, 작은 입 | gaze 기본 프레임 후보 |
| 19 | 선 눈, "3" 입 (분리 파츠) | 뽀뽀/삐짐 |
| 20 | 아래 보는 점 눈, 일자 입 | 부끄러움 |
| 21 | 동그란 눈, 고양이 :3 입 | 귀여운 반응 |
| 26 | 반감긴 눈, 살짝 미소, 볼 터치 | 편안한/만족 |
| 27 | 사각 화면 눈, 가는 미소 | content 대안 |
| 28 | 감은 선 눈, 웃는 입 | 웃음(눈 감고) |
| 30 | 매우 큰 동그란 눈, 작은 입 | 놀람/멍 |

---

## 2. 에셋 추출 전략

### 2.1 원칙

- **Figma 이미지를 그대로 활용** — 코드로 재작성하지 않음
- 각 Rosto를 **통째 PNG**로 사용하되, 눈동자 gaze tracking이 필요한 표정은 **파츠 분리**
- 캔버스 크기: 1280x720 (Figma 원본), 실제 렌더링은 디스플레이 해상도에 맞춰 스케일

### 2.2 추출 방식별 분류

#### A. Full-frame (통째 이미지) — 대부분의 표정

oneshot이나 고정 표정처럼 눈동자가 움직일 필요 없는 경우:

```
assets/expressions/
├── calm.png              ← rosto-02
├── attentive.png         ← rosto-22
├── sleepy.png            ← rosto-10
├── alert.png             ← rosto-29
├── startled.png          ← rosto-03
├── confused.png          ← rosto-14
├── welcome.png           ← rosto-04
├── happy.png             ← rosto-24
├── photo_ready.png       ← rosto-23
├── photo_snap.png        ← rosto-18
├── game_face.png         ← rosto-06
├── dance_face.png        ← rosto-07
├── smarthome_ok.png      ← rosto-18 (= photo_snap과 공유)
├── smarthome_fail.png    ← rosto-16
├── weather_face.png      ← rosto-25
├── petting.png           ← rosto-12
├── ko_defeated.png       ← rosto-11
└── boot.png              ← rosto-08
```

#### B. Compositable Parts (파츠 분리) — gaze tracking 대상

**calm** 및 **attentive**는 RIO가 가장 오래 머무는 표정이므로, 눈동자가 사용자를 따라가야 자연스러움.

Figma에서 SVG로 재추출하거나, PNG 파츠로 분리:

```
assets/expressions/parts/
├── calm/
│   ├── face_base.png     ← rosto-02에서 눈 영역 제거한 배경
│   ├── eye_left.png      ← 왼쪽 눈 (세로선 형태)
│   ├── eye_right.png     ← 오른쪽 눈
│   └── mouth.png         ← 입 (고정)
├── attentive/
│   ├── face_base.png     ← rosto-22에서 눈 영역 제거
│   ├── eye_left.png      ← 왼쪽 사각 눈
│   ├── eye_right.png     ← 오른쪽 사각 눈
│   └── mouth.png         ← 입 (고정)
└── blink/
    ├── calm_blink.png    ← calm 눈 감은 형태 (선)
    └── attentive_blink.png ← attentive 눈 감은 형태
```

> **Figma API 제한**: 현재 rate limit 상태이므로, 파츠 분리는 Figma에서 수동 export하거나
> 이미지 편집 도구로 rosto-02, rosto-22의 눈/입 영역을 crop하여 생성

### 2.3 Dim 처리

Away+Idle (dim)은 별도 에셋 없이 런타임에서 처리:
- `sleepy.png`을 렌더링하되 surface alpha를 30%로 설정 (pygame `set_alpha(77)`)
- 또는 어두운 오버레이 레이어 적용

---

## 3. 애니메이션 전략

### 3.1 눈 깜빡임 (Blink)

가장 중요한 살아있는 느낌의 핵심 애니메이션.

| 항목 | 값 |
|---|---|
| 방식 | 파츠 교체 (eye → blink eye → eye) |
| 주기 | 3~6초 랜덤 간격 |
| 지속 | 감기 80ms → 감긴 상태 60ms → 뜨기 80ms (총 ~220ms) |
| 적용 대상 | calm, attentive (파츠 분리된 표정) |
| 구현 | `eye_tracking.py`에서 blink timer 관리, 눈 파츠 swap |

```
Blink sequence (4 frames):
  [open] → [half-closed] → [closed] → [half-closed] → [open]
  0ms      80ms            140ms       200ms            220ms
```

필요 에셋 (blink 전용):
- `assets/expressions/parts/blink/calm_half.png` — calm 반쯤 감긴 눈
- `assets/expressions/parts/blink/calm_closed.png` — calm 완전 감긴 눈
- `assets/expressions/parts/blink/attentive_half.png`
- `assets/expressions/parts/blink/attentive_closed.png`

### 3.2 시선 추적 (Gaze Tracking)

| 항목 | 값 |
|---|---|
| 입력 | vision worker → `vision.face.moved` (normalized 0.0~1.0 좌표) |
| 방식 | eye 파츠의 blit offset 조절 |
| 범위 | 눈 중심 기준 좌우 ±15px, 상하 ±8px |
| 보간 | lerp (0.15 factor) — 부드러운 추종 |
| 적용 대상 | calm, attentive 상태에서만 |
| face_lost 시 | 눈 중심으로 복귀 (0.5s ease-out) |

```python
# eye_tracking.py 개념
target_x = (face_center_x - 0.5) * MAX_OFFSET_X  # ±15px
target_y = (face_center_y - 0.5) * MAX_OFFSET_Y  # ±8px
current_x += (target_x - current_x) * LERP_FACTOR
```

### 3.3 Oneshot 전환 애니메이션

oneshot은 현재 표정 위에 덧씌워진 뒤 자동 소멸. 전환 효과:

| Oneshot | 진입 | 유지 | 퇴장 | 총 지속 |
|---|---|---|---|---|
| startled | 즉시 교체 (0ms) | rosto-03 표시 | fade-out 200ms → 이전 표정 | ~600ms |
| confused | cross-fade 150ms | rosto-14 표시 | cross-fade 200ms | ~800ms |
| welcome | scale-in 200ms (0.8→1.0) | rosto-04 표시 | fade-out 300ms | ~1.5s |
| happy | 즉시 교체 | rosto-24 표시 | cross-fade 200ms | ~1s |

구현: full-frame 이미지를 통째로 교체. cross-fade는 두 surface의 alpha 블렌딩.

### 3.4 수면 애니메이션 (SleepUI)

Context=Sleepy, Activity=Idle일 때 `SleepUI` 전용 연출:

| 요소 | 설명 |
|---|---|
| 기본 표정 | rosto-10 (sleepy) |
| 눈 감기 루프 | 반감긴 → 완전 감긴 → 반감긴 (2s 주기) |
| Zzz 오버레이 | 우상단에서 Zzz 텍스트/아이콘이 떠오르는 반복 애니메이션 |
| 밝기 | 전체 화면 50% dim |
| wake-up | 얼굴 감지 시 → welcome oneshot으로 즉시 전환 |

Zzz 에셋:
```
assets/animations/
└── sleep/
    ├── zzz_01.png
    ├── zzz_02.png
    └── zzz_03.png    ← 크기별 3단계 (떠오르며 커짐)
```

### 3.5 댄스 모드 애니메이션

Executing(dance) 중:

| 요소 | 설명 |
|---|---|
| 기본 표정 | rosto-07 (dance_face) |
| 연출 | 표정 좌우 흔들림 (±5° rotation, 0.5s 주기) |
| 교대 표정 | rosto-24(happy) ↔ rosto-07 를 비트에 맞춰 교체 |
| 음표 오버레이 | 음표 아이콘이 양쪽에서 떠다님 |

### 3.6 사진 촬영 시퀀스

```
[attentive] → 카운트다운 시작 → [photo_ready(rosto-23)]
  → "3" → "2" → "1" → 셔터 flash
  → [photo_snap(rosto-18)] 0.5s → [happy(rosto-24)] 1s
  → 원래 표정 복귀
```

---

## 4. Layer 2 — Action Overlay 에셋

상태 머신의 Activity/Oneshot에 따라 Layer 1 위에 오버레이되는 요소들.

### 4.1 필요 에셋

```
assets/ui/overlays/
├── listening_indicator.png    ← 마이크/음파 아이콘 (ListeningUI)
├── search_indicator.png       ← 돋보기 (is_searching_for_user)
├── countdown_3.png            ← 사진 카운트다운 숫자
├── countdown_2.png
├── countdown_1.png
├── shutter_flash.png          ← 하얀 플래시 오버레이
├── timer_ring.png             ← 타이머 알림 아이콘 (AlertUI)
├── note_01.png                ← 음표 (댄스 오버레이)
├── note_02.png
├── heart_01.png               ← 하트 (petting 오버레이)
├── heart_02.png
├── heart_03.png
├── exclamation.png            ← 느낌표 (startled 보조)
└── question.png               ← 물음표 (confused 보조)
```

### 4.2 Figma 장식 에셋 활용

Figma 2nd Palette의 장식 요소 → idle 장면 변형용:

| Figma Node | 에셋 | 용도 |
|---|---|---|
| butterfly (47:108, 47:156) | `assets/animations/idle/butterfly.png` | Idle 장시간 시 배경 장식 |
| worm (47:111, 47:133) | `assets/animations/idle/worm.png` | Idle 장식 |
| ladybug (47:120) | `assets/animations/idle/ladybug.png` | Idle 장식 |
| bee (47:142) | `assets/animations/idle/bee.png` | Idle 장식 |

이들은 calm 상태에서 장시간 Idle일 때 화면에 간헐적으로 등장하는 연출에 사용.
(예: 나비가 화면 구석에서 날아다님 → 눈이 나비를 따라감)

---

## 5. Layer 3 — System HUD 에셋

화면 상/하단에 표시되는 시스템 정보 아이콘.

```
assets/ui/hud/
├── wifi_on.png
├── wifi_off.png
├── mic_on.png
├── mic_off.png
├── camera_on.png
├── battery_icon.png           ← (Pi UPS 사용 시)
├── weather_sunny.png
├── weather_cloudy.png
├── weather_rainy.png
├── weather_snowy.png
├── timer_active.png           ← 타이머 진행 중 표시
├── smarthome_connected.png
└── smarthome_disconnected.png
```

---

## 6. 디렉터리 구조 종합

```
assets/
├── figma_reference/           ← 원본 참조 (30개 PNG, 커밋 안 함)
│   ├── rosto-01.png ~ rosto-30.png
│
├── expressions/               ← Layer 1 Core Face
│   ├── calm.png
│   ├── attentive.png
│   ├── sleepy.png
│   ├── alert.png
│   ├── startled.png
│   ├── confused.png
│   ├── welcome.png
│   ├── happy.png
│   ├── photo_ready.png
│   ├── photo_snap.png
│   ├── game_face.png
│   ├── dance_face.png
│   ├── smarthome_fail.png
│   ├── weather_face.png
│   ├── petting.png
│   ├── ko_defeated.png
│   ├── boot.png
│   └── parts/                 ← Gaze tracking용 분리 파츠
│       ├── calm/
│       │   ├── face_base.png
│       │   ├── eye_left.png
│       │   ├── eye_right.png
│       │   └── mouth.png
│       ├── attentive/
│       │   ├── face_base.png
│       │   ├── eye_left.png
│       │   ├── eye_right.png
│       │   └── mouth.png
│       └── blink/
│           ├── calm_half.png
│           ├── calm_closed.png
│           ├── attentive_half.png
│           └── attentive_closed.png
│
├── animations/                ← 애니메이션 프레임/스프라이트
│   ├── sleep/
│   │   ├── zzz_01.png
│   │   ├── zzz_02.png
│   │   └── zzz_03.png
│   ├── idle/
│   │   ├── butterfly.png
│   │   ├── worm.png
│   │   ├── ladybug.png
│   │   └── bee.png
│   └── dance/
│       ├── note_01.png
│       └── note_02.png
│
├── sounds/                    ← 효과음 (이 문서 범위 외, 참고용)
│   ├── shutter.wav
│   ├── beep_ok.wav
│   ├── beep_fail.wav
│   ├── startled.wav
│   ├── snore.wav
│   └── happy.wav
│
└── ui/                        ← Layer 2 Overlay + Layer 3 HUD
    ├── overlays/
    │   ├── listening_indicator.png
    │   ├── search_indicator.png
    │   ├── countdown_3.png
    │   ├── countdown_2.png
    │   ├── countdown_1.png
    │   ├── shutter_flash.png
    │   ├── timer_ring.png
    │   ├── heart_01.png ~ heart_03.png
    │   ├── exclamation.png
    │   └── question.png
    └── hud/
        ├── wifi_on.png / wifi_off.png
        ├── mic_on.png / mic_off.png
        ├── camera_on.png
        ├── weather_*.png
        ├── timer_active.png
        └── smarthome_*.png
```

---

## 7. 구현 우선순위

### P0 — MVP (상태 머신 동작 확인)

1. **full-frame 8종** 추출: calm, attentive, sleepy, alert, startled, confused, welcome, happy (Away dim은 sleepy + dim 처리)
2. **blink 에셋 4종**: calm/attentive 각각 half, closed
3. **calm 파츠 분리**: face_base, eye_left, eye_right, mouth → gaze tracking 최소 동작

### P1 — Executing 장면

4. photo_ready, photo_snap, game_face, dance_face, weather_face, smarthome_fail, petting
5. 카운트다운 숫자 오버레이 (3, 2, 1)
6. listening_indicator, timer_ring

### P2 — 풍성한 연출

7. sleep 애니메이션 (zzz 시퀀스)
8. 하트/느낌표/물음표 오버레이
9. idle 장식 (나비, 벌레 등 Figma 장식 에셋)
10. HUD 아이콘 전체

---

## 8. Figma 에셋 추출 작업 체크리스트

### Figma에서 수동 작업 필요

- [ ] Rosto-02 (calm): 눈 2개 + 입을 별도 레이어로 export (SVG or PNG)
- [ ] Rosto-22 (attentive): 눈 2개 + 입을 별도 레이어로 export
- [ ] Blink 프레임: Figma에서 눈 감는 중간/닫힌 상태 직접 제작 (기존 Rosto에 없음)
- [ ] 장식 에셋 4종 (butterfly, worm, ladybug, bee) 개별 PNG export
- [ ] HUD 아이콘: Figma 또는 오픈소스 아이콘셋에서 수급

### 자동화 가능 (코드/스크립트)

- [ ] rosto-XX.png → 1280x720으로 리사이즈 (현재 2560x1440)
- [ ] Rosto별 이름 매핑에 따라 파일 복사+리네임
- [ ] dim 처리는 런타임 코드 (별도 에셋 불필요)
- [ ] cross-fade, scale 전환은 renderer.py에서 구현

---

## 9. renderer.py / face_compositor.py 연동 개요

```
Scene Selector → (mood, ui_layout) → Display Adapter

Display Adapter 내부:
  face_compositor.py
    ├── load_expression(mood) → full-frame 또는 parts
    ├── apply_gaze(face_coords) → eye offset 계산
    ├── apply_blink(timer) → blink frame 교체
    └── compose() → final Layer 1 surface

  renderer.py
    ├── Layer 1: face_compositor output
    ├── Layer 2: overlay sprites (from effect_planner)
    ├── Layer 3: hud icons (from system state)
    └── flip() → pygame display update
```

이 구조는 기존 tasklist의 T-016(layers.py), T-017(eye_tracking.py), T-019(renderer.py)와
새로 추가할 `face_compositor.py`로 구현됩니다.
