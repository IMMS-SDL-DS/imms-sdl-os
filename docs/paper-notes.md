# 📚 선행연구(논문) 읽고 정리

> 기록하기!!! -> 논문 읽고, 핵심 개념을 이해한 만큼 적어보기 
> "이해했다" = 남에게 설명할 수 있어야 함..

---

## AlabOS — Fei et al., Digital Discovery 2024

**한 줄 요약**
자율실험실이 여러 실험을 동시에, 충돌 없이, 자동으로 돌리게 해주는 운영체제
(MongoDB에 실시간으로 Sample, Device, Task, Experiment를 기록 -> 어떤 장비가 뭘 하고 있는지 항상 추적 가능)
**claude 정리**
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


"🔗AlabOS가 하는 걸 Prefect + MongoDB로 구현하는 게 나의 역할이구나."


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
- 실험실 전체를 하나의 OS로 본다 (마치 컴퓨터 OS가 CPU&메모리를 관리하듯이)
  -> 장비·DB·AI 최적화가 하나의 OS 안에서 돌아가는 구조
- DB 구조: device / job / devicelog 공통 테이블 +
  장비별 특화 테이블 (universal-specialized schema)
- SiLA2 프로토콜로 장비 통신 표준화
  → 새 장비 추가 = SiLA2 서버 설치만 하면 됨
- Atlas(Bayesian Optimization) 내장으로 AI 실험 계획 자동화
- 점진적 도입 가능: 장비 하나씩 추가하며 확장
- 유기 레이저 분자 발견 캠페인에서 실제 폐루프 검증

**내 연구에 적용할 부분:**
- device/job/devicelog 공통 테이블 구조를 MOF 실험에 맞게 변형
  → device: XRD, 반응기 등 (<- 장비 정보)
  → job: 각 실험 실행 기록
  → devicelog: 장비 로그 (온도, 압력 등 실시간 데이터)
- JSON 형식 명령 표준화 → 실험 조건을 JSON 스키마로 정의
- 점진적 도입 전략 참고 → XRD 하나부터 연결 시작

**AlabOS와 비교:**
- AlabOS: NoSQL(MongoDB), DAG 워크플로우, 처리량 강점
- ChemOS 2.0: SQL(PostgreSQL), SiLA2 표준화, 모듈성 강점
- 우리 연구(Prefect 기반)는 두 논문의 중간 어딘가
  → DAG 구조(AlabOS) + 표준화된 DB 설계(ChemOS 2.0)

  **추가 이해**
- AI 최적화 — Bayesian Optimization (Atlas)
- 실험 계획을 AI가 담당하는구나:
→ Atlas 라는 BO 패키지 사용
→ 이전 실험 결과를 보고 다음에 시도할 조건을 제안
→ 다목적 최적화 가능 (수율 + 순도 동시에)
→ DFT 시뮬레이션 결과도 함께 고려

**모르는 용어 정리:**
- SiLA2: 실험실 장비 통신 표준 프로토콜
  (HTTP가 웹 통신 표준이듯, SiLA2는 실험실 장비 통신 표준)
- NixOS: 소프트웨어 환경을 코드로 선언하는 OS
  (재현 가능한 환경 보장)
- AiiDA: 시뮬레이션 워크플로우 관리 소프트웨어
- DFT (Density Functional Theory): 분자 구조를 계산하는 양자화학 시뮬레이션
- Bayesian Optimization: 이전 실험 결과를 바탕으로
  다음 실험 조건을 AI가 제안하는 최적화 알고리즘
- HPLC-MS: 물질을 분리·분석하는 화학 장비
- Fog computing: 데이터를 원격 서버 아닌 로컬에서 처리하는 방식

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
