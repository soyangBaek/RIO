# Face UI Test Guide

구현 단계(P0/P1/P2)별 얼굴 UI 테스트 케이스.
각 케이스는 **상황 설명 → 기대 출력 → 사용 에셋/로직**을 명시합니다.

> 기준 문서: `scenarios.md`, `state-machine.md §6`, `face-asset-plan.md`
> 테스트 도구: `tools/face_demo.py` (시각), `tools/state_demo.py` (상태 전이), `tools/state_gui.py` (GUI)

---

## 테스트 도구 사용법

| 도구 | 실행 | 역할 |
|---|---|---|
| `D:\python\python.exe tools/face_demo.py` | pygame 창 | 표정 이미지/애니메이션 시각 확인 |
| `D:\python\python.exe tools/state_demo.py` | 터미널 | 이벤트 주입 → 상태 전이 + Mood/UI 파생 확인 |
| `D:\python\python.exe tools/state_gui.py` | tkinter 창 | 클릭으로 Context/Activity/Oneshot 조합 → Mood/UI 즉시 확인 |

**face_demo.py 조작:**
- `1`~`9`: primary mood / `0`,`-`,`=`,`BS`: secondary mood
- `F1`~`F7`: 시나리오 자동 재생
- `Tab`: 이미지/코드 모드 전환 / `D`: dim 토글 / 마우스: 시선

---

## P0 — MVP (상태 머신 기본 동작)

### P0-1. Primary 표정 9종

기본 상태 조합에서 올바른 표정 이미지가 표시되는지 확인.

| # | 상황 | 기대 표정 | 기대 UI | 표시 에셋 | 로직 |
|---|---|---|---|---|---|
| 1 | **RIO 전원 켜짐, 아무도 없음** — 부팅 직후 빈 방 | inactive | NormalFace(dim) | `sleepy.png` + dim overlay (alpha 30%) — `_MOOD_ALIASES`가 inactive→sleepy 매핑 | `face_compositor._apply_dim()` |
| 2 | **사람이 카메라에 잡힘** — 방에 사람이 걸어 들어옴 | calm | NormalFace | `calm.png` | `_render_image()` full-frame blit |
| 3 | **사람이 말 걸거나 터치함** — 적극적으로 상호작용 시작 | attentive | NormalFace | `attentive.png` | full-frame blit |
| 4 | **"오늘 날씨 어때?"** — 사람이 말을 걸고 있는 중 | attentive | ListeningUI | `attentive.png` | scene_selector: Listening → attentive 고정 |
| 5 | **오래 아무도 안 옴** — 방에 아무도 없는 채 2분 경과 | sleepy | SleepUI | `sleepy.png` | full-frame blit |
| 6 | **타이머 3분 끝!** — 설정한 타이머가 울림 | alert | AlertUI | `alert.png` | Alerting override (Context 무관) |
| 7 | **아무도 없는데 갑자기 소리** — 얼굴 없이 큰 소리 감지 | startled | (현재 UI 유지) | `startled.png` | oneshot ~600ms 후 자동 소멸 |
| 8 | **"알아듣지 못했어요"** — 음성 인식 실패 | confused | (현재 UI 유지) | `confused.png` | oneshot ~800ms 후 자동 소멸 |
| 9 | **오랜만에 주인 등장!** — 3초 이상 부재 후 얼굴 재감지 | welcome | (현재 UI 유지) | `welcome.png` | oneshot ~1.5s 후 자동 소멸 |
| 10 | **머리 쓰다듬기** — 터치스크린에서 쓰다듬기 제스처 | happy | (현재 UI 유지) | `happy.png` | oneshot ~1s 후 자동 소멸 |

**face_demo.py 테스트:**
```
키 1 → calm      (사람 있음, 평온)
키 2 → attentive (듣는 중 / 집중)
키 7 → sleepy    (졸림)
키 8 → alert     (타이머 울림!)
키 5 → startled  (깜짝 놀람)
키 6 → confused  (뭐라고?)
키 4 → welcome   (어서와!)
키 3 → happy     (기분 좋음)
키 9 → inactive  (sleepy 표정 + 자동 dim, Away+Idle)
D 키 → dim 토글  (밝기 30% ↔ 100%)
Tab  → 이미지/코드 모드 비교
```

**state_gui.py 검증:**
```
Context=Away + Activity=Idle    → Mood=inactive, UI=NormalFace(dim) 확인
                                  (렌더링은 sleepy.png + dim)
Context=Idle + Activity=Idle    → Mood=calm, UI=NormalFace 확인
Activity=Alerting 클릭          → Context와 무관하게 Mood=alert 확인
Oneshot=startled 클릭           → Mood=startled 로 override 확인
```

**확인 포인트:**
- [ ] 9개 mood 모두 서로 다른 이미지가 표시되는가
- [ ] dim 모드에서 이미지가 어둡게 보이는가 (배경 전체, alpha 30%)
- [ ] Tab으로 이미지/코드 전환 시 같은 mood가 다르게 렌더링되는가

---

### P0-2. Blink (눈 깜빡임)

살아있는 느낌의 핵심. 사람처럼 2~6초 간격으로 자연스럽게 눈을 깜빡여야 함.

| # | 상황 | 기대 출력 | 에셋/로직 |
|---|---|---|---|
| 1 | **평온한 대기 중** — calm 상태에서 가만히 있을 때 | 2~6초마다 눈 영역이 잠깐 감겼다 열림 (~200ms) | `_BlinkController` → `_render_image_blink()` |
| 2 | **집중해서 듣는 중** — attentive 상태 | 동일 blink 동작 | 동일 로직 |
| 3 | **깜짝 놀란 순간** — startled oneshot 중 | blink 없음 (놀란 눈 고정) | oneshot 중에는 blink 미적용 |
| 4 | **졸고 있음** — sleepy 상태 | blink 없음 (이미 반감긴 눈) | `mood in ("calm", "attentive")`만 blink |

**face_demo.py 테스트:**
```
키 1 (calm)     → 3~6초 기다리면 눈이 잠깐 감김
키 2 (attentive) → 동일 blink 확인
키 5 (startled)  → blink 발생하지 않아야 함
키 7 (sleepy)    → blink 발생하지 않아야 함
```

**현재 한계 (파츠 미분리):**
- 이미지 모드: 눈 영역에 배경색 사각형을 덮는 방식 (임시)
- 코드 모드: eye Y-scale로 부드러운 blink 동작
- 파츠 분리 후: eye 파츠를 blink 파츠로 swap하는 자연스러운 방식으로 교체 예정

**확인 포인트:**
- [ ] calm/attentive에서만 blink가 발생하는가
- [ ] blink 간격이 2~6초 랜덤인가 (고정 간격이 아닌가)
- [ ] blink 지속이 ~200ms로 짧은가 (눈에 거슬리지 않는가)

---

### P0-3. Gaze Tracking (시선 추적)

웹캠으로 감지한 사람 얼굴 위치를 따라 RIO의 눈동자가 움직이는 기능.
데모에서는 마우스 위치 = 사람 얼굴 위치로 시뮬레이션.

| # | 상황 | 기대 출력 | 에셋/로직 |
|---|---|---|---|
| 1 | **사람이 왼쪽으로 이동** — 마우스를 화면 좌측으로 | 눈동자가 왼쪽으로 따라감 | `saccade_x` → 눈 좌표 offset |
| 2 | **사람이 오른쪽 위로 이동** — 마우스를 우상단으로 | 눈동자가 우상향 | saccade_y는 x의 60% 범위 |
| 3 | **사람이 정면으로 복귀** — 마우스를 중앙으로 | 눈동자가 부드럽게 중앙 복귀 | lerp factor 0.15 |
| 4 | **이미지 모드에서 마우스 이동** | 변화 없음 (파츠 미분리 상태) | full-frame 이미지는 gaze 미지원 |

**face_demo.py 테스트:**
```
Tab  → 코드 모드 전환 (좌상단 "Mode: CODE" 확인)
키 1 → calm 상태에서 마우스를 좌우로 천천히 이동
     → 눈동자가 마우스를 따라가는지 확인
     → 빠르게 이동해도 부드럽게 추종하는지 확인 (튀지 않아야 함)

Tab  → 이미지 모드 전환
     → 마우스 이동해도 이미지가 변하지 않는 것 확인
```

**확인 포인트:**
- [ ] 코드 모드에서 마우스→눈동자 추종이 부드러운가
- [ ] 이미지 모드에서 gaze가 동작하지 않는 것이 명확한가
- [ ] (향후) 파츠 분리 후 이미지 모드에서도 eye offset이 동작할 것

---

### P0-4. Breathing (호흡 애니메이션)

정지 상태에서도 미세하게 움직여서 "살아있는 느낌"을 줌.

| # | 상황 | 기대 출력 | 에셋/로직 |
|---|---|---|---|
| 1 | **아무 표정에서 가만히 둠** | 이미지가 미세하게 위아래로 움직임 + 크기 변화 | `BreathingConfig` → `_blit_with_breathing()` |
| 2 | **4초간 관찰** | Y축 3px 범위 + scale 1.2% 범위의 사인파 진동 | 주기 4초 |

**face_demo.py 테스트:**
```
아무 키 누른 후 → 5초 이상 가만히 관찰
→ 얼굴 이미지가 살짝 "숨 쉬듯" 위아래로 움직이는지 확인
→ 거슬리지 않을 정도로 미세해야 함 (의식적으로 보면 보이는 수준)
```

**확인 포인트:**
- [ ] 이미지 모드에서 breathing이 동작하는가
- [ ] 코드 모드에서도 동일한 breathing이 보이는가
- [ ] 진폭이 너무 크지 않은가 (자연스러운 수준)

---

### P0-5. Oneshot 전환 (Cross-fade)

표정이 바뀔 때 "뚝" 끊기지 않고 부드럽게 전환되는지 확인.
실제로는 oneshot(순간 반응)이 발생했다가 원래 표정으로 돌아오는 흐름.

| # | 상황 | 기대 출력 | 에셋/로직 |
|---|---|---|---|
| 1 | **평온 → 깜짝 놀람** — 갑자기 큰 소리 | calm이 startled로 cross-fade (~350ms) | `_OneshotTransition` alpha 블렌딩 |
| 2 | **놀람 → 평온 복귀** — 놀란 뒤 600ms 후 | startled에서 calm으로 cross-fade | 동일 |
| 3 | **평온 → 반김 → 평온** — 주인 돌아옴, 1.5초 후 복귀 | 이미지가 부드럽게 3단계 전환 | 연속 transition |
| 4 | **표정 빠르게 연타** — 여러 mood 연속 변경 | 깜빡임/검은화면 없이 부드럽게 | transition 중 새 transition 즉시 교체 |

**face_demo.py 테스트:**
```
F1 → "깜짝 놀람" 시나리오
     calm → (부드럽게) → startled (0.6초 유지) → (부드럽게) → calm

F2 → "뭐라고?" 시나리오
     calm → confused (0.8초) → calm

F3 → "어서와!" 시나리오
     calm → welcome (1.5초) → calm

F4 → "기분 좋다!" 시나리오
     calm → happy (1초) → calm

키 1→3→5→7 빠르게 연타
     → 전환마다 검은 화면이 번쩍이지 않는지 확인
```

**확인 포인트:**
- [ ] cross-fade 도중 배경이 검게 번쩍이지 않는가
- [ ] 전환 시간이 체감상 ~300ms인가 (너무 빠르거나 느리지 않은가)
- [ ] 이미지 모드에서 전환이 동작하는가 (코드 모드는 즉시 교체)

---

### P0-6. Scene Selector Override 검증

특정 상태에서는 Context(장기 상황)와 무관하게 Activity(현재 행동)가 표정/UI를 강제 결정해야 함.

| # | 상황 | 기대 표정 | 기대 UI | 왜? |
|---|---|---|---|---|
| 1 | **졸고 있는데 타이머 울림** — Sleepy + Alerting | alert | AlertUI | 졸든 말든 알림은 반드시 표출 |
| 2 | **아무도 없는데 타이머 울림** — Away + Alerting | alert | AlertUI | 부재 중에도 알림 표출 |
| 3 | **사진 찍는 중 사람이 잠깐 프레임 이탈** — Executing(photo) + Context 변동 | attentive 유지 | CameraUI | 촬영 중 표정 흔들림 방지 (focus lock) |
| 4 | **스마트홈 실행 성공!** — Executing(smarthome) + happy oneshot | happy → attentive | NormalFace | oneshot이 focus lock보다 우선, 소멸 후 attentive 복귀 |

**state_gui.py 테스트:**
```
1. Context=Sleepy 클릭 → Activity=Alerting 클릭
   → Mood=alert 확인 (sleepy가 아님!)

2. Context=Away 클릭 → Activity=Alerting 클릭
   → Mood=alert, UI=AlertUI 확인

3. Activity=Executing → ExecKind=photo 클릭
   → Context를 Idle→Away→Engaged로 바꿔도 Mood=attentive 유지 확인

4. Activity=Executing + ExecKind=smarthome → Oneshot=happy 클릭
   → Mood=happy 확인 (oneshot이 focus lock 이김)
   → Oneshot=없음 클릭 → Mood=attentive 복귀
```

---

## P1 — Executing 장면

### P1-1. 사진 촬영 시퀀스

"사진 찍어줘"라고 말했을 때의 전체 표정 흐름.

| # | 상황 | 기대 표정 | 기대 UI | 표시 에셋 |
|---|---|---|---|---|
| 1 | **"사진 찍어줘" 듣는 중** | attentive | CameraUI | `attentive.png` |
| 2 | **카운트다운 시작** — 촬영 준비 | photo_ready | CameraUI | `photo_ready.png` (밝은 눈, 웃는 입) |
| 3 | **"3... 2... 1..."** — 카운트다운 진행 | photo_ready 유지 | CameraUI + 숫자 오버레이 | `photo_ready.png` + countdown |
| 4 | **찰칵!** — 셔터 순간 | photo_snap | CameraUI + flash | `photo_snap.png` (윙크!) |
| 5 | **잘 찍었다!** — 촬영 성공 | happy | NormalFace | `happy.png` (기쁨) |
| 6 | **원래대로** — 시퀀스 종료 | calm | NormalFace | `calm.png` |

**face_demo.py 테스트:**
```
F5 → 사진 촬영 시나리오 자동 재생
  0.0s: attentive   (준비)
  0.5s: photo_ready (밝은 눈, 웃는 입)
  1.5~3.5s: photo_ready 유지 (3... 2... 1... 구간)
  4.0s: photo_snap  (윙크!)
  4.5s: happy       (잘 찍었다!)
  5.5s: calm        (복귀)

좌상단 "Mood: xxx" 텍스트가 각 단계에서 바뀌는지 함께 확인
```

**확인 포인트:**
- [ ] photo_ready(밝은 눈)와 photo_snap(윙크)이 구별되는가
- [ ] 전체 시퀀스가 ~6초에 자연스럽게 완료되는가
- [ ] happy에서 calm으로의 복귀 전환이 부드러운가

---

### P1-2. Executing(kind)별 표정

각 기능 실행 중 어떤 표정을 보여줘야 하는지.

| # | 상황 | 기대 표정 | 표시 에셋 | 비고 |
|---|---|---|---|---|
| 1 | **"춤 춰!"** — 댄스 실행 중 | attentive (기본) | `dance_face.png` (물결 입) | effect_planner가 dance_face로 override 예정 |
| 2 | **"게임 하자!"** — 게임 모드 실행 중 | attentive (기본) | `game_face.png` (픽셀 패턴) | GameUI 전용 표정 |
| 3 | **"오늘 날씨 어때?"** — 날씨 조회 중 | attentive (기본) | `weather_face.png` (큰 원형 눈) | 조회 중 표정 |
| 4 | **"에어컨 꺼줘"** — 스마트홈 실행 중 | attentive | `attentive.png` | 기본 attentive 유지 |
| 5 | **에어컨 꺼짐! 성공!** — 스마트홈 명령 성공 | happy (oneshot) | `happy.png` | oneshot이 focus lock override |
| 6 | **에어컨 응답 없음... 실패** — 스마트홈 명령 실패 | confused (oneshot) | `confused.png` | 실패 피드백 |

**face_demo.py 테스트:**
```
키 =  → game_face  (게임 모드 표정 확인)
키 BS → dance_face (댄스 모드 표정 확인)
키 -  → photo_snap (윙크 확인)
키 0  → photo_ready (밝은 눈 확인)
```

**state_gui.py 검증:**
```
Activity=Executing + kind=weather → Mood=attentive, UI=NormalFace
Activity=Executing + kind=photo   → Mood=attentive, UI=CameraUI
Activity=Executing + kind=game    → Mood=attentive, UI=GameUI
```

> 참고: 현재 scene_selector는 Executing 시 mood를 항상 attentive로 파생.
> dance_face, game_face 등 kind별 전용 표정은 effect_planner/executor가
> 직접 renderer에 override하는 구조로 구현 예정 (T-030, T-031).

---

### P1-3. 특수 반응 표정

일반 mood 외에 특정 상황에서만 나오는 전용 표정.

| # | 상황 | 표시 에셋 | 비고 |
|---|---|---|---|
| 1 | **머리 쓰다듬기** — 터치스크린에서 좌우 스트로크 | `petting.png` (하트 눈, 미소) | happy oneshot + 전용 표정 |
| 2 | **"불 꺼줘" 실패** — 스마트홈 HTTP 타임아웃 | `smarthome_fail.png` (울상 눈, 슬픈 입) | confused oneshot + 전용 표정 |
| 3 | **게임에서 짐** — 참참참 패배 등 | `ko_defeated.png` (X 눈, 꺾인 입) | game service가 표정 override |
| 4 | **RIO 부팅 중** — 전원 켜지고 초기화 화면 | `boot.png` (다이아 눈, 로봇 느낌) | main.py 초기화 시 표시 |

**테스트 방법:**
```
face_demo.py에서는 직접 키 매핑 없음 (secondary 키로 이미지 확인만 가능).
실제 트리거는 effect_planner 구현 후 state_demo.py의 이벤트 주입으로 테스트:
  state_demo.py: 15 (터치 쓰다듬기) → happy/petting 반응 확인
  state_demo.py: 13 (태스크 실패) → confused/smarthome_fail 반응 확인
```

---

## P2 — 풍성한 연출

### P2-1. Sleep 애니메이션

RIO가 오랫동안 혼자 있을 때 졸다가, 주인이 돌아오면 반갑게 깨어나는 흐름.

| # | 상황 | 기대 출력 | 에셋/로직 |
|---|---|---|---|
| 1 | **아무도 안 온 지 2분** — Sleepy 상태 진입 | 반감긴 눈 + SleepUI + 50% dim | `sleepy.png` + dim overlay |
| 2 | **계속 졸고 있음** — Sleepy 유지 | Zzz가 우상단에서 반복적으로 떠오름 | `zzz_01~03.png` (미제작) → 코드 fallback: "Zzz" 텍스트 |
| 3 | **주인 돌아옴!** — Sleepy 중 얼굴 재감지 | welcome oneshot → calm으로 깨어남 | `welcome.png` → `calm.png` cross-fade |

**face_demo.py 테스트:**
```
F6 → sleep/wake 시나리오 자동 재생
  0s:   calm     (평온)
  1s:   sleepy   (반감긴 눈... 졸려...)
  3s:   inactive (sleepy 표정 + 자동 dim, 완전 어두움)
  6s:   welcome  (어! 왔어? 반가워!)
  7.5s: calm     (다시 평온)

관찰:
  - sleepy에서 inactive로 전환 시 자동 dim 적용되는 과정
  - welcome 진입 시 확 밝아지는 느낌
```

**미구현 에셋:**
- `assets/animations/sleep/zzz_01~03.png` — Figma에서 제작 필요

---

### P2-2. 댄스 모드 애니메이션

"춤 춰!"라고 말했을 때 RIO가 신나게 흔들리는 연출.

| # | 상황 | 기대 출력 | 에셋/로직 |
|---|---|---|---|
| 1 | **"춤 춰!" 인식됨** — 댄스 모드 진입 | dance_face 표정 | `dance_face.png` (물결 입) |
| 2 | **춤추는 중** | 얼굴이 좌우로 흔들림 (±5°, 0.5초 주기) | `pygame.transform.rotate()` |
| 3 | **비트 전환** | dance_face ↔ happy 교대 | 두 이미지 교대 blit |
| 4 | **음표 날아다님** | 양쪽에서 음표 아이콘 떠다님 | `note_01.png`, `note_02.png` (미제작) |

**미구현 에셋:**
- `assets/animations/dance/note_01.png`, `note_02.png`

---

### P2-3. Layer 2 오버레이

표정(Layer 1) 위에 겹쳐지는 아이콘/이펙트들.

| # | 상황 | 오버레이 | 에셋 |
|---|---|---|---|
| 1 | **음성 듣는 중** — "오늘 날씨..." 말하는 동안 | 마이크/음파 아이콘 (하단) | `listening_indicator.png` (미제작) |
| 2 | **소리는 들리는데 얼굴이 안 보임** — 누가 말하는 거지? | 돋보기 아이콘 추가 | `search_indicator.png` (미제작) |
| 3 | **사진 카운트다운** — 3... 2... 1... | 큰 숫자 화면 중앙에 | `countdown_3/2/1.png` (미제작) |
| 4 | **찰칵! 셔터 순간** | 하얀 플래시 전체 화면 | `shutter_flash.png` 또는 코드 white fill |
| 5 | **타이머 울림!** — 딩동딩동 | 알림 벨 아이콘 | `timer_ring.png` (미제작) |
| 6 | **머리 쓰다듬기 반응** — 기분 좋아~ | 하트가 화면에서 떠오름 | `heart_01~03.png` (미제작) |
| 7 | **깜짝 놀람 보조** — 뭐야?! | 느낌표 아이콘 | `exclamation.png` (미제작) |
| 8 | **혼란 보조** — 뭐라고? | 물음표 아이콘 | `question.png` (미제작) |

---

### P2-4. Idle 장식 (Figma 2nd Palette)

평온하게 오래 대기 중일 때 화면에 생기를 주는 장식 요소.

| # | 상황 | 오버레이 | 에셋 |
|---|---|---|---|
| 1 | **calm 30초 이상 유지** — 심심한데... | 나비가 화면 구석에서 날아다님 | `butterfly.png` (미제작) |
| 2 | **calm 장시간 유지** | 벌레가 기어다님 | `worm.png` (미제작) |
| 3 | **calm 장시간 유지** | 무당벌레 등장 | `ladybug.png` (미제작) |
| 4 | **calm 장시간 유지** | 벌이 날아다님 | `bee.png` (미제작) |

> 나비가 날아다니면 RIO 눈이 나비를 따라가는 연출도 가능 (gaze 응용)

---

### P2-5. Layer 3 HUD 아이콘

화면 상/하단에 항상 또는 조건부로 표시되는 시스템 상태 정보.

| # | 상황 | HUD 요소 | 위치 | 에셋 |
|---|---|---|---|---|
| 1 | **항상** | Wi-Fi 연결 상태 | 우상단 | `wifi_on/off.png` (미제작) |
| 2 | **항상** | 마이크 활성 상태 | 우상단 | `mic_on/off.png` (미제작) |
| 3 | **날씨 조회 완료 후** | 날씨 아이콘 (맑음/흐림/비/눈) | 좌하단 | `weather_*.png` (미제작) |
| 4 | **타이머 돌아가는 중** | 남은 시간 카운트 | 우하단 | `timer_active.png` (미제작) |
| 5 | **스마트홈 연결됨** | 연결 상태 표시 | 우상단 | `smarthome_*.png` (미제작) |

---

## 전체 시나리오 → 에셋 매핑 요약

### 완성 에셋 (17종)

| 에셋 | Figma 원본 | 언제 보이는가 | 상태 |
|---|---|---|---|
| `calm.png` | rosto-02 | 사람 있음, 평온한 대기 | done |
| `attentive.png` | rosto-22 | 듣는 중, 기능 실행 중, 사람과 적극 상호작용 | done |
| `sleepy.png` | rosto-10 | 오래 아무도 안 옴, 졸림 | done |
| `alert.png` | rosto-29 | 타이머 울림, 긴급 알림 | done |
| `startled.png` | rosto-03 | 갑작스런 소리, 예상 못한 등장 | done |
| `confused.png` | rosto-14 | 음성 인식 실패, 명령 실패 | done |
| `welcome.png` | rosto-04 | 오랜만에 주인 등장! | done |
| `happy.png` | rosto-24 | 쓰다듬기, 명령 성공, 기분 좋은 순간 | done |
| `photo_ready.png` | rosto-23 | 사진 카운트다운 중 (3... 2... 1...) | done |
| `photo_snap.png` | rosto-18 | 셔터 순간 (윙크), 스마트홈 성공 | done |
| `game_face.png` | rosto-06 | 게임 모드 실행 중 | done |
| `dance_face.png` | rosto-07 | 댄스 모드 실행 중 | done |
| `smarthome_fail.png` | rosto-16 | 스마트홈 명령 실패, 기기 응답 없음 | done |
| `weather_face.png` | rosto-25 | 날씨 조회 중 | done |
| `petting.png` | rosto-12 | 머리 쓰다듬기 반응 (하트 눈) | done |
| `ko_defeated.png` | rosto-11 | 게임에서 짐 (X 눈) | done |
| `boot.png` | rosto-08 | RIO 부팅/초기화 화면 | done |

### 미제작 에셋

| 카테고리 | 에셋 | 언제 필요한가 | 제작 방법 |
|---|---|---|---|
| 파츠 | calm/attentive 눈 분리 | 눈동자가 사람을 따라가려면 | Figma에서 눈/입 별도 export |
| 파츠 | blink half/closed (4종) | 자연스러운 눈 깜빡임 | Figma에서 감긴 눈 직접 제작 |
| 오버레이 | listening_indicator | "듣고 있어요" 표시 | Figma 또는 아이콘셋 |
| 오버레이 | search_indicator | "누가 말하는 거지?" 표시 | Figma 또는 아이콘셋 |
| 오버레이 | countdown 3/2/1 | 사진 카운트다운 숫자 | Figma에서 숫자 제작 |
| 오버레이 | timer_ring | 타이머 울림 아이콘 | Figma 또는 아이콘셋 |
| 오버레이 | heart 1~3 | 쓰다듬기 하트 이펙트 | Figma에서 제작 |
| 오버레이 | exclamation, question | 놀람/혼란 보조 아이콘 | Figma에서 제작 |
| 애니메이션 | zzz 1~3 | 졸고 있을 때 Zzz | Figma에서 제작 |
| 애니메이션 | note 1~2 | 댄스 중 음표 | Figma에서 제작 |
| 장식 | butterfly, worm, ladybug, bee | 심심할 때 화면 장식 | Figma 2nd Palette export |
| HUD | wifi, mic, weather, timer 등 | 시스템 상태 표시 | Figma 또는 아이콘셋 |

---

## Oneshot 중첩 정책 테스트

여러 순간 반응이 동시에 발생했을 때 어떤 것이 보여야 하는지.
**state_demo.py**로 테스트.

| # | 상황 | 기대 결과 | 표시 에셋 |
|---|---|---|---|
| 1 | **반기는 중에 갑자기 놀람** — welcome(pri 20) 진행 중 startled(pri 30) | 즉시 startled로 교체 (높은 priority 선점) | `startled.png` |
| 2 | **기쁜데 또 기쁜 일** — happy(20) 진행 중 20% 시점에 happy 재트리거 | 무시 (같은 표정 깜빡임 방지) | `happy.png` 유지 |
| 3 | **기쁨 거의 끝날 때 반김** — happy(20) 진행 중 85% 시점에 welcome(20) | 교체 허용 (80% 이상 경과 시 같은 priority도 교체) | `welcome.png` |
| 4 | **놀란 중에 기쁜 일** — startled(30) 진행 중 happy(20) | 무시 (낮은 priority는 항상 무시) | `startled.png` 유지 |
| 5 | **놀람+기쁨 동시 발생** | startled만 표출 (높은 priority 우선, 큐잉 없음) | `startled.png` |

**state_demo.py 테스트:**
```
1 (얼굴 감지) → 3 (음성 시작) → 11 (unknown intent)
→ confused oneshot 확인
→ 즉시 15 (쓰다듬기)
→ happy가 confused를 교체하는지 확인 (priority 같음, 시점에 따라 다름)
```

---

## 통합 시나리오 (End-to-end)

### E2E-1: RIO의 하루 — 부팅부터 수면까지

```
state_demo.py에서 s (시나리오 자동 재생):

 1. 부팅 완료     → 빈 방, 어두운 대기      → inactive (sleepy+dim), NormalFace(dim)
 2. 사람 등장     → 얼굴 감지!              → calm, NormalFace
 3. 터치          → 상호작용 시작           → attentive, NormalFace
 4. "오늘 날씨"   → 듣는 중                → attentive, ListeningUI
 5. 날씨 intent   → 날씨 조회 중            → attentive, NormalFace
 6. 조회 성공     → 기분 좋다!              → happy oneshot → calm
 7. "사진 찍어"   → 듣는 중                → ListeningUI
 8. 사진 intent   → 사진 촬영 중            → CameraUI
 9. 촬영 성공     → 잘 찍었다!              → happy oneshot
10. 타이머 울림   → 딩동!                  → alert, AlertUI
11. 터치 확인     → 알림 종료              → calm, NormalFace
12. 사람 나감     → 얼굴 사라짐            → calm 유지 (잠깐)
13. 갑자기 소리   → 누구야?!              → startled oneshot + Listening
```

face_demo.py의 F7 (전체 mood 순회)과 조합하여
시각적으로 모든 17개 표정이 올바르게 렌더링되는지 확인.
