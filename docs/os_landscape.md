# 🗺️ MOF SDL OS — landscape (SDL OS 지형도 그려보고, 현재 플젝의 위치 생각)

>
> (1) 기존 SDL OS들 사이에서 우리가 지금 어디 있는지,
> (2) "가상 OS 기반 스케줄링"으로 가려면 뭐가 더 필요한지 정리한 것.

---

## 1. SDL OS 지형도 (기존 5개 시스템 기반)

| | **ChemOS(원조)**<br>2020 | **ChemOS 2.0**<br>2024 | **AlabOS**<br>2024 | **IvoryOS**<br>2025 | **UniLabOS**<br>2025 | **OCTOPUS**<br>2024 | **MOF SDL OS**<br>(우리) |
|---|---|---|---|---|---|---|---|
| **핵심 철학** | SDL 개념 최초 구현, 6모듈 구조 | "실험실=OS" | 워크플로우 실증·처리량 | 코드 1줄→자동 웹UI | 실험실을 AI가 직접 제어 | 멀티유저 스케줄링 | 실제 프로토콜의 정확한 실행 |
| **워크플로우 모델** | 설정 파일 기반 | UNIX 철학 | DAG (task 분해) | Prep→Exp→Cleanup 3단계 | A/R/A&R 추상화 | Job→Task→Action 계층 | Phase→Step (Prefect flow) |
| **DB** | - | SQL (모듈형) | MongoDB | - | Dual-Topology | Job Storage | **MongoDB (4 컬렉션)** |
| **자원 충돌 방지** | - | - | 자원 예약 + 데드락 방지 | - | Resource Tree | Masking Table | **원자적 락 (idle/busy)** ✅ |
| **스케줄링/병렬화** | - | - | 대기열 관리 | - | - | **Job Parallelization + CPS** | ❌ 아직 없음 |
| **가상/시뮬레이션** | - | **시뮬레이터 지원** | - | - | Digital Twin | - | ❌ 아직 없음 |
| **장치 통신** | - | SiLA2 표준 | - | Python 클래스 자동 UI화 | ROS2/DDS 분산 | TCP/IP + UDP heartbeat | 인터페이스 자리만 정의 (RobotDriver) |
| **데이터 계보 추적** | - | - | - | - | CRUTD (Transfer 트랜잭션) | - | **Reference Edge** ✅ |
| **재시도 안전성** | - | - | - | - | - | - | **오퍼레이션별 분리 정책** ✅ |
| **실증 규모** | 5개 실험 | 1개 워크플로우 | 3,500+ 샘플 (1.5년) | 6개 SDL | 4개 환경 | 시뮬레이션 벤치마크 | 57 Task × 1 프로토콜 (하드웨어 실증 전) |

---

## 2. 현 위치 (ai 기반 피드백)

### ✅ 강점
- **Reference Edge 기반 데이터 계보 추적**: UniLabOS의 CRUTD(Transfer 트랜잭션) 개념과 유사한 걸, 더 단순한 형태(`input_refs`/`output_refs`)로 이미 구현. 어떤 Sample이 어떤 Task로부터 나왔는지 역추적 가능.
- **원자적 장비 락**: OCTOPUS의 masking table, AlabOS의 자원 예약과 같은 목적을, MongoDB 원자적 연산(`find_one_and_update`)으로 더 가볍게 구현. 실제 race condition 테스트(mongomock)까지 완료.
- **재시도 안전 정책**: 이 부분은 참고한 5개 논문 어디에도 명시적으로 다루지 않은 부분 — "통신 에러 재시도가 물리적 이중 실행으로 이어질 수 있다"는 문제를 오퍼레이션별로 분리해서 해결한 건 우리만의 기여.
- **실제 프로토콜 100% 반영**: 다른 시스템들은 범용 프레임워크를 먼저 만들고 실험을 나중에 끼워 맞추는 경우가 많은데, 우리는 실제 Zr-BTC 프로토콜(19종 Unit Operation, 57단계)을 그대로 이식하는 데서 시작해서 **당장 쓸 수 있는 정확도**를 확보했음.

### ❌ 추가적으로 필요한 부분
1. **스케줄링/병렬화 (OCTOPUS의 핵심 기여)** — 지금은 "한 실험을 정확히 순서대로 실행"만 함. 여러 실험이 동시에 들어왔을 때 "누가 먼저, 누구는 대기"를 결정하는 로직이 없음.
2. **시뮬레이션/가상 장치 (ChemOS 2.0, UniLabOS)** — 지금은 `simulated_robot_driver`처럼 코드 안에 하드코딩된 가짜 함수뿐. "장치 없이도 전체 시스템을 가상으로 돌려볼 수 있는 계층"은 없음.
3. **표준화된 장치 통신 프로토콜 (SiLA2, ROS2/DDS)** — 지금은 `RobotDriver`라는 우리만의 임시 인터페이스. 표준 프로토콜은 아님 (지금 단계에선 오버엔지니어링일 수 있어 의도적으로 보류한 부분).

---

## 3. "가상 OS 기반 최적 Scheduling" 

"가상 OS 기반으로 실험되면서 최적 scheduling" :

### (A) 가상 OS (Virtual/Simulated Execution Layer)
실제 장비 없이도, 우리 시스템 전체(Task 검증 → 장비 락 → 실행 → DB 기록)를 그대로 돌려볼 수 있는 계층.
- **이미 절반은 있음**: `save_to_db=False` 모드, `simulated_*_driver` 함수들이 이 역할의 초기 버전
- **필요한 확장**: 각 오퍼레이션의 **실행 시간(device execution time)**과 **대기 시간(device standby time)**을 현실적으로 모사하는 시뮬레이터 (OCTOPUS 논문이 벤치마크에 썼던 것과 동일한 개념 — 예: HEAT은 실제로 24시간 걸리므로, 시뮬레이션에서도 "24시간이 걸린다"는 걸 시간 압축해서 재현)

### (B) 최적 Scheduling
OCTOPUS 논문이 제안한 3가지 기법을 그대로 참고할 수 있음:
1. **Job Parallelization** — 한 실험이 "대기 시간"(예: HEAT 24시간)에 들어가 있는 동안, 다른 실험이 같은 장비의 빈 시간을 활용해 진행
2. **Task Optimization (Masking Table)** — 우리가 이미 만든 Device 락의 확장판. 지금은 "장비 하나 대 Task 하나"만 체크하는데, 여러 장비를 동시에 필요로 하는 Task까지 고려해야 함
3. **CPS (Closed-Packing Schedule)** — 여러 실험의 배치(batch)를 장비 자원에 맞춰 쪼개서 최대한 빈틈없이 채우는 알고리즘

### 어떻게 스키마로 확장할지 
지금 만든 `Task.device_id`, `Device.status`, `SAFE_TO_RETRY_OPERATIONS` 구조가 이미 "오퍼레이션 단위로 장비 요구사항을 명시"하는 형태라서, 스케줄러가 이 정보를 읽어서 병렬화 여부를 판단하는 게 구조적으로 어렵지 않음. **즉 지금 설계가 스케줄링 확장을 이미 염두에 둔 형태였다는 게 강점.**

---

## 4. 대략적인 로드맵

| 단계 | 내용 | 참고할 기존 시스템 |
|---|---|---|
| 1 | 오퍼레이션별 실행시간/대기시간 데이터 정의 (프로토콜에 이미 일부 있음: HEAT 24h, SONICATE 10min 등) | OCTOPUS 벤치마크 방식 |
| 2 | 여러 Experiment를 동시에 큐(waiting/executing/holding)로 관리하는 Job Scheduler 계층 추가 | OCTOPUS Job Scheduler |
| 3 | 장비 대기 시간을 활용한 Job Parallelization 구현 | OCTOPUS |
| 4 | 위 스케줄러를 "가상 실행"만으로 테스트할 수 있는 시뮬레이션 모드 강화 | ChemOS 2.0 시뮬레이터 |
| 5 | (선택) CPS 알고리즘으로 배치 분할 최적화 | OCTOPUS |

---

## 5. 피드백 질문

- Mehdi 박사님 Proposal에서 "최적 scheduling"이 구체적으로 어떤 목표 함수를 최소화/최대화하려는 건지 (처리량? 대기시간? 자원 활용률?) — OCTOPUS는 "job waiting time"을 핵심 지표로 삼았는데, 우리도 같은 지표를 쓰면 될지
- 스케줄링 계층이 지금 MOF SDL OS(MultiDose 실증용)와 같은 코드베이스로 갈지, 별도 모듈로 분리할지
- 시뮬레이션에 쓸 "가상 장비"가 실제 MultiDose/XRD 스펙을 얼마나 정밀하게 반영해야 하는지 (단순 시간 지연만 흉내내면 되는지, 아니면 실패율까지 통계적으로 모사해야 하는지)
