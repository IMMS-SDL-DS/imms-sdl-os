# 📅 연구 진행 기록

> 매주 배운 것, 만든 것, 막혔던 것을 모두 기록!! 일종의 TROUBLE SHOOTING 
---

## Day 1 — 사전 준비 (2026.7.1)

### 읽은 논문
- [x] AlabOS (Fei et al., 2024) — Digital Discovery

### 정리 메모
> AlabOS 핵심 요약
- 자율실험실 = Sample / Device / Task / Experiment 4가지로 구성
- 실험 순서 = DAG (Prefect의 Flow 구조랑 동일!)
- Resource Manager = 장비 충돌 방지 핵심
- MongoDB로 모든 상태 실시간 추적
- A-Lab 1.5년 3,500샘플 실증 → 우리가 만들 시스템의 교과서

> 느낀 점
- Prefect의 @flow / @task 구조가 AlabOS의 Experiment / Task 구조와
  거의 동일하다는 걸 깨달음. 논문을 먼저 읽고 Prefect를 배우니
  왜 이런 구조인지 이해가 훨씬 빠름
- MOF 실험에서 Sample = MOF 샘플, Device = XRD 장비,
  Task = XRD 측정 작업으로 바로 매핑 가능
---

## Day 2 — (2026.7.2)

### 읽은 논문
- [x] ChemOS 2.0 (Sim et al., 2024) — Matter
- [x] IvoryOS (2025) — Nature Communications

### 배운 것
> ChemOS 2.0 핵심 요약
- 실험실 = OS (UNIX 철학: 모듈화·연동·JSON 통신)
- DB 구조: device/job/devicelog 공통 + 장비별 특화 테이블
- SiLA2로 모든 장비 통신 표준화 → 새 장비 추가가 쉬워짐
- Atlas BO 내장 → AI가 다음 실험 조건 자동 제안
- 점진적 도입 가능 → 장비 하나씩 붙여나가는 전략
> IvoryOS 핵심 요약
- Python 코드 → 자동 웹 UI 생성 (코드 1줄)
- 3단계 워크플로우: Prep → Experiment → Cleanup
- 3가지 실행 모드: Repeat / Configurable / BO 자동화
- 6개 SDL 실제 검증, 진입장벽 최소화

### 깨달은 점
- AlabOS의 DAG 구조 + ChemOS 2.0의 표준화된 DB 설계를
  Prefect로 구현하는 게 해당 연구실에서 내 역할의 핵심
- device/job/devicelog 세 테이블이 핵심 뼈대
  → MOF XRD 실험에 맞게 변형하는 게 첫 번째 과제구나...

---

## Day 3 — (2026.7.3)

### 읽은 논문
- [x] UniLabOS (2025) — arXiv
- [x] Tom et al. SDL 리뷰 (2024) — Chemical Reviews

### 배운 것
> ChemOS 원조 핵심 요약
- SDL OS 개념의 시작점 (2020)
- 6개 독립 모듈 + 중앙 워크플로우 관리자 구조
- Bayesian BO로 AI가 다음 실험 조건 자동 제안
- 실제 pH 7.0 목표 → 17번째 실험에서 7.001 달성
  

> UniLabOS 핵심 요약
- A/R/A&R로 모든 실험실 요소 추상화
- Dual-Topology: 논리 트리 + 물리 그래프
- CRUTD: 물질 이동을 트랜잭션으로 관리
- 분산 엣지-클라우드, 네트워크 장애에도 실험 지속

### 전체 논문 최종 정리
원조 ChemOS(2020) → AlabOS + ChemOS 2.0(2024)
→ IvoryOS + UniLabOS(2025)
→ 우리 연구실 SDL OS (Prefect 기반)

### 앞으로 나의 역할
"UniLabOS의 A/R/A&R + CRUTD 개념,
AlabOS의 DAG 워크플로우,
ChemOS 2.0의 표준화된 DB 설계를
Prefect + MongoDB로 MOF 실험에 구현하는 것"

### 더 해볼 것
- [ ] Prefect 설치 후 example_flow.py 실행
- [ ] MongoDB vs PostgreSQL 어떤 게 우리 연구에 맞는지 검토
- [ ] MOF 실험용 device/job/devicelog 스키마 초안 작성

---

<!-- 이하 동일 형식으로 주차별 추가 -->

## Day 4 — 실제 MOF 프로토콜 기반 스키마 v2 (2026.7.7)

### 계기
- 실험팀 노션에서 실제 MOF 실험 프로세스 문서를 못 찾음 → 기존 MOF 실험 과정 공유받음
- 실제 프로토콜 PDF(`MOF_실험_공정팀_final.pdf`, Zr-BTC MOF Synthesis) 저장
- 추가로 OCTOPUS 논문(장비 스케줄링/멀티유저 SDL OS)과
  지식그래프 기반 소재 합성 이론 리포트(ActionGraph 등)도 참고

### 한 일
- [x] 실제 프로토콜의 Unit Operation Schema(OP-01~19)를 `src/database/models.py`에
      Pydantic 모델로 전부 이식 (operation별 파라미터 타입 검증)
- [x] 프로토콜 전체(Phase A~G, Step별 시약/장비/파라미터)를
      `data/protocols/zr_btc_mof_protocol.json`으로 구조화
- [x] `src/pipeline/zr_btc_synthesis_flow.py` — 이 JSON을 읽어서 실제로 Prefect flow로
      실행되는지 테스트 (57개 Task, REPEAT 처리 포함 시뮬레이션 성공)
- [x] `docs/db_schema.md` v2로 전면 개정 (v1은 archive로 이동)
- [x] `data/schema/mongo_schema_v2.json` — MongoDB $jsonSchema validator 작성

### 깨달은 점
- "Task 컬렉션이 Module 단위인지 Task 단위인지" 계속 헷갈렸던 문제가
  실제 프로토콜 보니까 명확해짐: **Phase(A~G) = Module, Step(A-1, B-2...) = Task**
- 프로토콜의 `order_critical` (D-1: 혼합 순서 L→M 반드시 준수) 같은 안전 제약은
  단순 참고사항이 아니라 Prefect flow에서 강제로 검증해야 하는 로직으로 다뤄야 함
- Washing 단계(F-2~F-6, DMF/Acetone 각 3회)처럼 반복되는 구간은
  펼쳐서 저장(task 12개)하되 `repeat_of` 필드로 그룹 정보만 남기는 게
  개별 반복의 성공/실패 추적에 유리함
- Opentron Flex가 Phase A,B,C,D,F,G에 걸쳐 계속 쓰임 → 여러 실험 병렬 실행 시
  이 장비를 쓰는 Task끼리는 반드시 직렬화해야 함 (OCTOPUS의 masking table 문제 그대로)

### 다음에 할 것
- [ ] MongoDB 실제 연결 (지금은 전부 시뮬레이션)
- [ ] 실제 장비(Opentron Flex 등) Python API 연결
- [ ] Device 상태 실시간 갱신 로직 (idle/busy) 구현

---

## Day 5 — MongoDB Atlas 연결 (2026.7.7)

### 한 일
- [x] MongoDB Atlas(클라우드) 클러스터 재개 및 연결 문자열 확인
- [x] `.env` / `.env.example` 로 접속 정보 분리 (비밀번호는 git에 안 올라가게)
- [x] `src/database/mongo_client.py` 작성:
      - `.env` 읽어서 Atlas 연결, ping으로 연결 확인
      - `mongo_schema_v2.json` validator로 4개 컬렉션 생성/갱신
      - Experiment/Task/Device/Sample Pydantic 모델을 upsert하는 저장 헬퍼
      - `get_sample_lineage()` — Sample 하나의 Provenance(어느 Task가 만들었고 어디에 쓰였는지) 역추적
- [x] `zr_btc_synthesis_flow.py`가 실제로 Task를 MongoDB에 저장하도록 연결
      (`.env` 없어도 자동으로 시뮬레이션 모드로 fallback 되게 처리함)
- [x] 테스트 7개 전부 통과 확인

### 겪은 문제 (트러블슈팅)
- Git Bash에서 `cd` 없이 홈 디렉토리에서 `git init`을 실행해서 VS Code 앱 데이터까지
  스캔하려던 사고 발생 → `.git` 폴더 위치 잘못됨을 `pwd`로 확인 후 삭제, 올바른 clone 폴더로 이동해서 해결
- `.gitignore`에 `*.json` 전체 무시 규칙이 있어서 `data/protocols/*.json`이 계속 안 올라감
  → `!data/protocols/*.json` 예외 규칙 추가
- `git push` 시 origin에 로컬에 없는 커밋이 있어 rejected → `git pull` 후
  `docs/paper-notes.md`에서 merge conflict 발생 (논문 정리했던 내용 중의 일부 head 등 충돌) →
  `<<<<<<<`/`=======`/`>>>>>>>` 마커만 제거하고 양쪽 내용 다 살려서 해결
- mongodb 접속시 실시간 ip 주소를 계속 허용해줘야함!!
  SSL 에러도 ip 허용으로 인해 발생하는 경우 많다고 함.
  
### 다음에 할 것
- [ ] 실제 장비(Opentron Flex 등) Python API 연결 <- 장비 접근 권한 확인 필요,,
- [ ] Device 상태 실시간 갱신 로직 (idle/busy) 구현

### 피드백 
> "SDL OS를 멋지게 만들어서 다른 기관들에게 자랑스럽게 소개할 수 있는 OS,
> 그리고 이걸 이용해서 다양한 공정 및 소재 자율실험 원천기술의 백본으로 사용하면 좋을 것 같음
---

## Day 6 — MultiDose 공부 (2026.7.8)
### MultiDose란
- 다양한 SBS 포맷 바이알에 분말을 분주하는 자동화 고체 분주 시스템
- Mettler Toledo XPR 저울과 협동로봇(cobot)을 결합해서 재현 가능한 분말 분주를 구현
- 구체적으로는 Universal Robots의 UR3e cobot 팔에 Robotiq의 Hand-E 그리퍼를 장착한 구조

### 기존 스키마와 겹치는 부분 
- 로봇팔(UR3e) = Device.device_type: "solid_dispenser" 역할
- Mettler Toledo XPR 저울 = 이미 mass_metal, mass_ligand 검증에 쓰던 바로 그 장비 (OP-02 VERIFY_MASS)
> 지금 만들어놓은 OP-01 DISPENSE_SOLID + OP-02 VERIFY_MASS 오퍼레이션 그 자체
> 즉 B-1, C-1(고체 분주) + B-2, C-2(질량 검증) Task가 실제 첫 하드웨어 연동 대상이 됨

### 확인해야 하는 부분 - API 연동 가능 여부
- 외부에서 Python으로 직접 스크립팅 가능한 오픈 API가 기본 제공인지는 불확실
- UR 로봇 SDK나 Mettler Toledo 저울 API로 직접 저수준 제어를 만들고 있을 가능성
> 인터페이스 계약을 정의하는게 필요
- [ ] src/pipeline/zr_btc_synthesis_flow.py의 execute_step() 안 [SIM] 부분을 실제로 누가 어떤 함수로 대체할지 (예: dispense_solid(reagent, mass_mg, vessel) 같은 함수 시그니처를 로봇 제어팀이 구현하고, 내 코드는 그 함수를 호출만 하는 구조)
- [ ] VERIFY_MASS 실행 후 실측값(mass_metal_mg=95.2 같은)이 어떤 형식으로 Prefect flow로 돌아올지 (JSON? 리턴값? 파일?)
- [ ] 로봇/저울 제어 코드가 이미 Python으로 되어있는지, 아니면 별도 프로세스로 떠 있어서 소켓/API로 통신해야 하는지

---
## Prefect 공부 (2026.7.9)
### Prefect란
- 파이썬 함수를 "워크플로우"로 관리해주는 오케스트레이션 도구
-  마치 택배 추적 시스템처럼: 우리가 만든 flow/task 하나하나가 "출발 → 진행 중 → 도착/실패" 상태를 자동으로 기록하고, 실패하면 재시도(retries)도 자동으로 해줌
> from prefect import flow
> @flow
> def my_workflow() -> str:   return "Hello, world!"
> my_workflow()  # 그냥 평범한 함수처럼 호출

- execute_step이 실행되다가 예외(에러)가 발생하면, Prefect가 자동으로 한 번 더 이 함수를 처음부터 다시 실행
- 그리고 그 재시도까지 실패하면 그때 최종 Failed 상태
- (예시) MultiDose 로봇한테 명령을 보냈는데, 마침 로봇이 이전 동작 중이라 순간적으로 통신이 씹혀서 타임아웃 에러!
- **retries=1**  Prefect가 "어 실패했네, 한 번 더 해보자" 하고 자동으로 재시도해서 넘어가게 됨
