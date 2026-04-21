# Face Expression Scenario Map

RIO가 사용하는 모든 표정(PNG) 에셋과, 각 표정이 언제 표시되는지 정리한 문서.

---

## 에셋 목록

| #  | 파일명              | asset_key        | 사용 여부  |
|----|---------------------|------------------|------------|
| 1  | `alert.png`         | `alert`          | ✅ 사용    |
| 2  | `angry_idle.png`    | `angry_idle`     | ✅ 사용    |
| 3  | `angry_talking.png` | `angry_talking`  | ✅ 사용    |
| 4  | `attentive.png`     | `attentive`      | ✅ 사용    |
| 5  | `boot.png`          | `boot`           | ❌ 미사용  |
| 6  | `bored_old.png`     | `bored_old`      | ❌ 미사용  |
| 7  | `calm.png`          | `calm`           | ✅ 사용    |
| 8  | `confused.png`      | `confused`       | ✅ 사용    |
| 9  | `cry.png`           | `cry`            | ✅ 사용    |
| 10 | `cute.png`          | `cute`           | ✅ 사용    |
| 11 | `cute_lips.png`     | `cute_lips`      | ❌ 미사용  |
| 12 | `dance_face.png`    | `dance_face`     | ✅ 사용    |
| 13 | `happy.png`         | `happy`          | ✅ 사용    |
| 14 | `lovely.png`        | `lovely`         | ✅ 사용    |
| 15 | `photo_cute.png`    | `photo_cute`     | ✅ 사용    |
| 16 | `photo_ready.png`   | `photo_ready`    | ✅ 사용    |
| 17 | `photo_snap.png`    | `photo_snap`     | ❌ 미사용  |
| 18 | `robot_idle.png`    | `robot_idle`     | ✅ 사용    |
| 19 | `robot_left.png`    | `robot_left`     | ❌ 미사용  |
| 20 | `robot_right.png`   | `robot_right`    | ❌ 미사용  |
| 21 | `sleepy.png`        | `sleepy`         | ✅ 사용    |
| 22 | `smarthome_fail.png`| `smarthome_fail` | ✅ 사용    |
| 23 | `startled.png`      | `startled`       | ✅ 사용    |
| 24 | `triangle_tear.png` | `triangle_tear`  | ❌ 미사용  |
| 25 | `weather_face.png`  | `weather_face`   | ✅ 사용    |
| 26 | `welcome.png`       | `welcome`        | ✅ 사용    |
| 27 | `wet_tear.png`      | `wet_tear`       | ✅ 사용    |

---

## 시나리오별 표정 + 효과음 매핑

### 1. 사진 촬영

| 상황                       | 표정           | fallback     | 효과음                |
|----------------------------|----------------|--------------|----------------------|
| 촬영 대기 (PHOTO/CameraUI) | `photo_ready`  | `attentive`  | —                    |
| 촬영 완료 직후 (900ms)     | `photo_cute`   | `happy`      | `camera_shutter.mp3` |

### 2. 스마트홈 제어

| 상황             | 표정              | fallback    | 효과음               |
|------------------|-------------------|-------------|---------------------|
| 명령 성공        | `cute`            | `happy`     | `pride-emote.mp3`   |
| 명령 실패        | `smarthome_fail`  | `confused`  | `surprise-emote.mp3`|

### 3. 댄스 모드

| 상황             | 표정           | fallback | 효과음       | 비고                          |
|------------------|----------------|----------|-------------|-------------------------------|
| 댄스 실행 중     | `dance_face`   | `happy`  | `dance.mp3` | RGB 플래시 오버레이 추가       |

### 4. 게임 모드

| 상황             | 표정           | fallback     | 효과음 |
|------------------|----------------|--------------|--------|
| 게임 실행 중     | `wet_tear`     | `attentive`  | —      |

### 5. 날씨 조회

| 상황             | 표정              | fallback     | 효과음 |
|------------------|--------------------|--------------|--------|
| 날씨 조회 중     | `weather_face`     | `attentive`  | —      |

### 6. 제스처 반응 (Oneshot)

| 제스처              | Oneshot  | 표정                              | fallback    | 지속시간         | 효과음                 |
|---------------------|----------|-----------------------------------|-------------|------------------|------------------------|
| 주먹 (fist)         | `angry`  | `angry_idle` ↔ `angry_talking`    | `startled`  | 2초 (0.5s 교대)  | `distress-emote.mp3`   |
| 양손 손바닥 (both)   | `lovely` | `lovely`                          | `happy`     | 2.5초            | `love-emote.mp3`       |

### 7. 애니메이션 오버레이 연동

| 오버레이 키 | 표정        | fallback    | 트리거                   | 효과음                |
|-------------|-------------|-------------|--------------------------|----------------------|
| `cry`       | `cry`       | 현재 mood   | 쓰다듬기 (touch stroke)  | `pleased-emote.mp3`  |
| `welcome`   | `welcome`   | 현재 mood   | 손 흔들기 / 까꿍         | `pleased-emote.mp3`  |
| `startled`  | `startled`  | 현재 mood   | 핑거건 (finger_gun)      | `shocked-emote.mp3`  |

### 8. 수면 / 대기

| 상황                              | 표정           | fallback | 효과음                         |
|-----------------------------------|----------------|----------|--------------------------------|
| 수면 상태 (SLEEPY 진입~퇴장)       | `sleepy`       | —        | `sleepy-emote.mp3` (무한 반복)  |
| 수면 오버레이 + sleepy_with_face   | `robot_idle`   | `calm`   | `sleepy-emote.mp3` (계속 재생)  |
| 수면 오버레이 (일반)               | `sleepy`       | —        | `sleepy-emote.mp3` (계속 재생)  |
| mood == `inactive`                | `sleepy`       | —        | `sleepy-emote.mp3` (계속 재생)  |

### 9. 기본 Mood 매핑 (위 조건에 해당 없을 때)

| Mood         | 표정         | fallback | 효과음 |
|--------------|--------------|----------|--------|
| `calm`       | `calm`       | —        | —      |
| `attentive`  | `attentive`  | `calm`   | —      |
| `happy`      | `happy`      | `calm`   | —      |
| `alert`      | `alert`      | `calm`   | —      |
| `confused`   | `confused`   | `calm`   | —      |
| `startled`   | `startled`   | `calm`   | —      |
| `welcome`    | `welcome`    | `calm`   | —      |
| `sleepy`     | `sleepy`     | `calm`   | —      |
| 기타         | mood → `calm`| `calm`   | —      |

### 10. 기타 이벤트 효과음 (표정 변화 없음)

| 이벤트                    | 효과음                 | 비고                    |
|---------------------------|------------------------|------------------------|
| 음성 인식 시작             | `listening_cue.mp3`    | 다른 SFX 없을 때만      |
| 타이머 만료                | `timer_ring.mp3`       | —                      |
| 타이머 등록 완료           | `timer_ring.mp3`       | —                      |
| 작업 실패                  | `surprise-emote.mp3`   | —                      |
| 탭 (TOUCH_TAP)            | scenes.yaml의 sfx      | —                      |

---

## 효과음 파일 매핑 (SFX_FILES)

| SFX 키            | 파일                    | 재생 조건                         |
|--------------------|-------------------------|-----------------------------------|
| `startled`         | `shocked-emote.mp3`     | finger_gun 제스처                 |
| `welcome`          | `pleased-emote.mp3`     | wave / peekaboo 제스처            |
| `happy`            | `pleased-emote.mp3`     | touch stroke / peekaboo           |
| `dance`            | `dance.mp3`             | 댄스 모드 실행                    |
| `shutter`          | `camera_shutter.mp3`    | 사진 촬영 완료                    |
| `alert`            | `timer_ring.mp3`        | 타이머 만료                       |
| `timer_registered` | `timer_ring.mp3`        | 타이머 등록 완료                  |
| `success`          | `pride-emote.mp3`       | 스마트홈 성공 / 게임 성공         |
| `error`            | `surprise-emote.mp3`    | 스마트홈 실패 / 작업 실패         |
| `listening_cue`    | `listening_cue.mp3`     | 음성 인식 시작                    |
| `sleepy`           | `sleepy-emote.mp3`      | SLEEPY 상태 동안 (무한 반복, 퇴장 시 정지) |
| `angry`            | `distress-emote.mp3`    | fist 제스처 (angry oneshot)       |
| `lovely`           | `love-emote.mp3`        | both_palms 제스처 (lovely oneshot)|

---

## 특수 효과

| 표정                | 효과                                                    |
|---------------------|---------------------------------------------------------|
| `dance_face`        | RGB 컬러 플래시 오버레이 (빨강→초록→파랑, 0.5초 주기)    |
| `calm`, `attentive` | 눈 깜빡임 오버레이 적용                                  |
| `angry` oneshot     | `angry_idle` ↔ `angry_talking` 0.5초 간격 자동 교대      |

---

## 미사용 에셋

| 파일                 | 설명                                        |
|----------------------|---------------------------------------------|
| `boot.png`           | 부팅 화면용 (예정)                           |
| `bored_old.png`      | 이전 버전 지루함 표정                        |
| `cute_lips.png`      | 대체 귀여움 표정                             |
| `photo_snap.png`     | 촬영 순간 표정 (현재 photo_cute로 대체)      |
| `robot_left.png`     | 로봇 좌측 시선 (예정)                        |
| `robot_right.png`    | 로봇 우측 시선 (예정)                        |
| `triangle_tear.png`  | 삼각 눈물 표정                               |
