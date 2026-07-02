# 📚 선행연구(논문) 읽고 정리

> 기록하기!!! -> 논문 읽고, 핵심 개념을 이해한 만큼 적어보기 
> "이해했다" = 남에게 설명할 수 있다.

---

## AlabOS — Fei et al., Digital Discovery 2024

**한 줄 요약**
자율실험실이 여러 실험을 동시에, 충돌 없이, 자동으로 돌리게 해주는 운영체제

AlabOS 해결법:

Task가 시작 전에 "나 이 장비 쓸게요" 라고 예약
다른 Task는 그 장비 못 씀 (예약 중 표시)
Task 끝나면 자동으로 반납
Python with 문으로 구현 → 실패해도 자동 반납


④ Manager-Worker 구조
[대시보드] ← 사람이 명령
     ↓
[Experiment Manager] → 실험을 Task 그래프로 파싱
[Task Manager]       → Task 실행·모니터링
[Resource Manager]   → 장비 예약·충돌 방지
[Device Manager]     → 실제 장비에 명령 전달
     ↓
[Task Actor]         → 실제로 Task 실행하는 일꾼
Manager들은 MongoDB로 서로 소통. 사람은 웹 대시보드에서 모니터링.

⑤ 실제로 A-Lab에서 검증됨

1.5년간 3,500개 샘플 합성
하루 최대 149개 처리
장비 16종 28대 연결
XRD, furnace, 로봇팔 등 실제 연결


🔗 셩이 연구(Prefect + MOF DB)랑 연결
AlabOS셩이가 할 것MongoDB로 Sample/Device/Task 상태 관리DB 스키마 설계Task 순서를 DAG로 표현Prefect 워크플로우 (Prefect도 DAG 구조!)Resource Manager가 장비 상태 추적장치 연결 인터페이스Logger로 실험 데이터 저장데이터 파이프라인
AlabOS가 하는 걸 Prefect + MongoDB로 구현하는 게 셩이 역할이야!


📝 docs/paper-notes.md에 넣을 내용
아래 그대로 복붙해서 AlabOS 섹션 채워넣어:
markdown## AlabOS — Fei et al., Digital Discovery 2024

**핵심 아이디어:**
- 자율실험실을 Sample / Device / Task / Experiment 4가지로 모델링
- 실험 순서를 DAG(방향 비순환 그래프)로 표현 → 병렬 실행 가능
- Resource Manager가 장비 예약·충돌 방지 (Python with 문으로 자동 반납)
- Manager-Worker 구조: Experiment/Task/Resource/Device Manager + Task Actor
- MongoDB(NoSQL) 백엔드로 유연한 스키마 + 실시간 상태 추적
- A-Lab에서 1.5년간 3,500개 샘플 실증, 하루 최대 149개 처리

**내 연구에 적용할 부분:**
- Sample/Device/Task/Experiment 4가지 컬렉션 구조를 MOF 실험 DB에 그대로 적용
- AlabOS의 DAG 워크플로우 = Prefect의 Flow/Task 구조와 동일
  → Prefect로 AlabOS와 같은 DAG 파이프라인 구현 가능
- Resource Manager 개념을 참고해 장치 상태(idle/occupied/paused) DB에 기록
- Logger 구조 참고해 실험 데이터를 device_signal / result / system_log로 분류 저장 (data pipeline)

**모르는 용어 정리:**
- DAG (Directed Acyclic Graph): 방향이 있고 순환이 없는 그래프. 실험 순서 표현에 사용
- Pydantic: Python 데이터 검증 라이브러리. 입력값 형식 자동 체크
- MODBUS / TCP/IP / XML-RPC: 장비와 컴퓨터가 통신하는 프로토콜
- Manager-Worker 구조: 관리자(Manager)가 일꾼(Worker)에게 작업 분배하는 아키텍처
- RPC (Remote Procedure Call): 다른 프로세스의 함수를 원격으로 호출하는 방식

---

## ChemOS 2.0 — Sim et al., Matter 2024

**핵심 아이디어:**
- 실험실 전체를 하나의 OS로 본다
- device / job / devicelog 테이블 구조
- SiLA2 기반 모듈 통신

**내 연구에 적용할 부분:**
>

**모르는 용어:**
>

---

## IvoryOS — Nature Communications 2025

**핵심 아이디어:**
>

**내 연구에 적용할 부분:**
>

---

## UniLabOS — arXiv 2025

**핵심 아이디어:**
>

**내 연구에 적용할 부분:**
>

---

## Tom et al. SDL 리뷰 — Chemical Reviews 2024

**핵심 아이디어:**
- DMTA 사이클 (Design→Make→Test→Analyze)
- 자율화 수준 Level 1~5 분류
- FAIR 원칙이 핵심 과제

**내 연구에 적용할 부분:**
>
