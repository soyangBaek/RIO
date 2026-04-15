# Adapters

이 디렉토리는 외부 장치, OS 자원, 네트워크 서비스와 만나는 어댑터 계층입니다.

현재 RIO의 기준 하드웨어/입출력은 아래와 같습니다.

- `audio/`: 마이크 입력, VAD, STT 전처리
- `speaker/`: TTS 및 효과음 출력
- `vision/`: 웹캠 프레임 입력과 비전 추론 연결
- `touch/`: 터치스크린 입력 이벤트 처리
- `display/`: 3-layer UI 렌더링과 눈동자/시선 애니메이션
- `camera/`: 사진 촬영과 저장
- `weather/`: 날씨 API 호출
- `home_client/`: 스마트홈 제어용 로컬 home-client HTTP 호출

원칙:

- 상위 도메인 로직은 어댑터 내부 구현을 몰라야 합니다.
- 눈 방향 반응은 `display/` 애니메이션으로 처리합니다.
- 스마트홈 요청은 `home_client/` 어댑터를 통해서만 외부로 나갑니다.

