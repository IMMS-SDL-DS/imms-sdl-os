# 📚 선행연구(논문) 읽고 정리

> 기록하기!!! -> 논문 읽고, 핵심 개념을 이해한 만큼 적어보기 
> "이해했다" = 남에게 설명할 수 있어야 함..

---

## AlabOS — Fei et al., Digital Discovery 2024

**한 줄 요약**
자율실험실이 여러 실험을 동시에, 충돌 없이, 자동으로 돌리게 해주는 운영체제
(MongoDB에 실시간으로 Sample, Device, Task, Experiment를 기록 -> 어떤 장비가 뭘 하고 있는지 항상 추적 가능)


**claude 정리**
- Task가 시작 전에 "나 이 장비 쓸게요" 라고 예약
- 다른 Task는 그 장비 못 씀 (예약 중 표시)
- Task 끝나면 자동으로 반납
- Python with 문으로 구현 → 실패해도 자동 반납


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
> IvoryOS란 Python 코드만 있으면 자동으로 웹 인터페이스가 생성되는 SDL 오케스트레이터 — 코딩 없이도 실험실을 제어할 수 있게 해주는 도구

- Python 코드 한 줄 추가로 자동 웹 인터페이스 생성
  → 장비 바뀌면 UI도 자동 업데이트 (plug-and-play)
    → 코드를 자동으로 UI로 변환
- "ivoryos.run(__name__)"
  -> Python 클래스의 모든 메서드가 자동으로 웹 UI로 변환됨!
  <-> SDL 만들 때마다 GUI도 따로 개발할 필요 없어짐.

- 3가지 인터페이스: Direct Control / Workflow Design / Execution
     - Direct Control : 장비를 직접 제어. 버튼 누르면 바로 실행
     - Workflow Design : 드래그앤드롭으로 실험 순서 설계
     - Workflow Execution : 설계한 워크플로우 실행·모니터링  
- 워크플로우 3단계: Preparation(1회) → Experiment(반복) → Cleanup(1회)
- 실행 모드 3종: Repeat / Configurable(human-in-the-loop) / Bayesian BO (closed-loop)
- #param 표기로 동적 파라미터 정의 → 매 반복마다 조건 변경 가능
- 6개 서로 다른 SDL에서 실제 검증
- 첫 설치·연동에 10~30분밖에 안 걸림


**AlabOS·ChemOS 2.0과 비교:**
| | AlabOS | ChemOS 2.0 | IvoryOS |
|---|---|---|---|
| 강점 | 처리량·실증 | 표준화 | 빠른 적용·민주화 |
| GUI | 전용 대시보드 | Streamlit | 자동 생성 웹 UI |
| 진입장벽 | 높음(프레임워크 학습) | 중간 | 낮음(코드 1줄) |
| 대상 | 완성된 SDL | 실험 계획 중심 | 개발 중인 SDL |


**실제 SDL에서의 검증**
- 항체-약물 결합 플랫폼
- 정제 최적화 플랫폼
- 유동화학 플랫폼
- 액액 추출 플랫폼
- 용해도 스크리닝 플랫폼
- 유도체화 샘플링 플랫폼
       -> 모두 같은 IvoryOS 코드로 제어 가능. 장비가 달라도 Python 클래스만 있으면 된다!!
  
**내 연구에 적용할 부분:**
> Prefect 파이프라인이 완성되면 IvoryOS처럼
  웹 인터페이스로 연구실 사람들이 쉽게 쓸 수 있게 확장 가능
- 워크플로우 3단계 구조(Prep → Experiment → Cleanup)를
  MOF 실험 파이프라인 설계에 그대로 적용 가능
- #param 동적 파라미터 개념을 Prefect flow 설계에 참고

**모르는 용어 정리:**
- Flask: Python 경량 웹 프레임워크. 웹 서버 만들 때 씀
- WebSocket: 서버-클라이언트 실시간 양방향 통신 프로토콜
  (실험 진행 상황을 실시간으로 UI에 반영할 때 사용)
- Serialization: 코드의 구조(클래스·메서드)를 데이터 형식으로 변환
- OOP (Object-Oriented Programming): 객체 지향 프로그래밍
- Bayesian Optimization (Ax platform): Meta가 만든 BO 라이브러리
- Human-in-the-loop: AI 루프에 사람이 개입하는 구조
- plug-and-play: 설정 없이 바로 연결해서 쓸 수 있는 방식

---

## UniLabOS — arXiv 2025
**한 줄 요약**
"실험실을 AI가 직접 제어할 수 있는 운영체제로 만든다 — 장비·물질·실험 흐름을 하나의 통합된 시스템으로 추상화"

**핵심 아이디어:**
- A/R/A&R 추상화: 실험실 모든 요소를 Resource/Action/Action&Resource로 분류
- R: 물질을 담기만 하는 것
- A: 동작만 하는 것
- A&R: 담으면서 동작도 하는 것 (eg. 액체 핸들러, 가열교반기)
  
- Dual-Topology: 논리 트리(소유권) + 물리 그래프(연결 경로) 이중 표현
- CRUTD: 기존 CRUD에 Transfer 추가 → 물질 이동을 트랜잭션으로 관리
>      CRUTD = Create / Read / Update / Transfer / Delete
                              ↑
                    물질 이동을 트랜잭션으로 관리
                    
- 분산 엣지-클라우드: ROS 2/DDS 기반, 네트워크 장애에도 실험 지속
- LLM+MCP로 자연어 → 실험 실행 파이프라인 구현
- 4가지 실제 환경에서 검증 (단일 장치 → 분산 3호스트 → P2P 폐루프)

**기존 OS들과 비교 (논문 내 정리):**
| OS | 강점 | 한계 |
|---|---|---|
| ChemOS | SDL 개념 정립 | 특정 장치 종속 |
| ChemOS 2.0 | 모듈화·SiLA2 | 특정 도메인 |
| AlabOS | 워크플로우 실증 | 고체 합성 특화 |
| UniLabOS | 위 모두 통합+AI-native | 초기 단계 |

**내 연구에 적용할 부분:**
- CRUTD 개념 참고 → MOF 실험 데이터에 Transfer 개념 적용
  (샘플이 어디서 왔는지 추적하는 이력 관리)
- A/R/A&R 분류를 MOF 실험 DB 스키마에 적용
  → XRD 장비 = A&R, 시약 바이알 = R, 펌프 = A
- Resource Tree 구조를 Prefect 파이프라인 설계에 참고

**모르는 용어 정리:**
- ROS 2 (Robot Operating System 2): 로봇 소프트웨어 개발 프레임워크
- DDS (Data Distribution Service): 분산 시스템 간 실시간 데이터 통신 미들웨어
- Digital Twin: 물리 장치의 가상 복제본. 실제 실행 전에 시뮬레이션 가능
- AST (Abstract Syntax Tree): 코드를 트리 구조로 파싱한 것. 코드 분석에 사용
- CRUD: Create/Read/Update/Delete — 기본 데이터베이스 연산
- CRUTD: CRUD + Transfer — 물질 이동을 포함한 확장 연산
- MCP (Model Context Protocol): LLM이 외부 도구와 통신하는 프로토콜
- P2P (Peer-to-Peer): 중앙 서버 없이 노드끼리 직접 통신
- Provenance: 데이터의 출처·이력 추적 정보

---

## ChemOS (원조) — Roch et al., PLOS ONE 2020

**핵심 아이디어:**
- "SDL이라는 개념 자체를 처음 소프트웨어로 구현한 논문 — 이후 모든 SDL OS의 출발점"
- 6개 독립 모듈 구조:
  AI 알고리즘 / 로봇 플랫폼 / 특성화 장비 /
  DB 관리 / 연구자 인터페이스 / 결과 분석
  -> 각 모듈이 독립적으로 작동하고, 설정 파일 하나만 바꾸면 새 실험에 바로 적용 가능.
- Bayesian (AI) 최적화 3종 지원: Phoenics, SMAC, Spearmint
- NLP 챗봇으로 이메일·Twitter·Slack 통해 원격 제어 가능
- 실제 5가지 실험 검증: 색깔·pH·밀도·칵테일·HPLC 캘리브레이션
- 핵심 성과: pH 7.0 목표 → 17번째 실험에서 7.001 달성

**(기억) 기존 방식과의 차이: Closed-Loop**
- 기존 방식
  > 사람이 실험 설계 → 실험 → 결과 분석 → 다시 사람이 설계 (느리고 인간 직관에 의존)
- ChemOS 방식
  > AI가 실험 조건 제안 → 로봇이 실험 → 결과 자동 수집 → AI가 학습 → 더 나은 조건 제안 → 반복 (인간 개입 최소화)
- 중요한 건 실험 결과가 다음 실험에 자동으로 반영된다는 것!!

**원조 → 2.0 → AlabOS 발전 계보:**
- ChemOS(2020): 개념 정립, 6모듈 구조, Bayesian BO 도입
- ChemOS 2.0(2024): UNIX 철학 적용, SiLA2 표준화, SQL DB
- AlabOS(2024): DAG 워크플로우, 자원 예약, MongoDB, 실증

**내 연구에 적용할 부분:**
- "설정 파일 하나로 새 실험 적용" 철학
  → Prefect flow도 config 기반으로 설계하면 재사용성 높아짐
- 모듈 독립성 원칙
  → DB 모듈 / 파이프라인 모듈 / 장치 모듈을 분리해서 설계
- 닫힌 루프의 핵심: 실험 결과가 다음 실험 설계에 자동 반영
  → 파이프라인의 최종 목표와 동일

**핵심 용어 정리:**
- NLP (Natural Language Processing): 자연어 처리.
  사람의 말을 컴퓨터가 이해하게 하는 기술
- Bayesian Optimization: 이전 실험 결과로 다음 조건을 추론하는 최적화
- Edisonian approach: 에디슨식 시행착오 접근법
  (수천 번 실험해서 답 찾기) — SDL이 이걸 대체하려는 것
- Phoenics: ChemOS 팀이 직접 만든 BO 알고리즘.
  탐색(exploration)과 활용(exploitation) 균형 조절 가능
- FIFO (First-In-First-Out): 먼저 들어온 요청을 먼저 처리하는 방식
