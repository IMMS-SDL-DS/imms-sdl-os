# 🧪 IMMS SDL-OS — Self-Driving Laboratory Operating System

> **이화여자대학교 IMMS (Institute for Multiscale Materials and Systems)**
> 국가연구소(NRL 2.0) 1기 학부 인턴 연구 기록
> 연구자: 손시영 | 소속: 데이터사이언스학과 | 기간: 2026.07 – 

> **참여 이유**
> - 화학신소재공학과와 데이터사이언스의 융합
> - 실무적인 경험 취득
> - 국가연구소의 과제에 기여 (이화여대에 큰 규모의 SDL 설립)

---

## 연구 개요

MOF(Metal-Organic Framework) 자율실험실(SDL)의 **운영체제(OS) 구축**을 위한
데이터베이스 시스템 및 파이프라인 자동화 연구.

실험 장비에서 생성되는 데이터를 AI가 학습할 수 있는 형태로
자동 수집·정제·저장하는 **Prefect 기반 워크플로우 파이프라인**을 설계하고,
실제 장치와 연결하는 것을 목표로 한다.

핵심 구성 요소:
- **Task/Action 스키마**: 실험 하나를 16단계(또는 그 이상)의 Action으로 쪼개어 추적 (`src/database/models.py`)
- **안전 검사 로직**: RETRACT 실패 시 이어지는 DOOR_CLOSE 같은 안전 필수 단계를 자동 차단 (`src/pipeline/action_driver.py`)
- **Prefect + MongoDB 통합**: 실행하는 즉시 Prefect 대시보드와 MongoDB Atlas 양쪽에 실제로 기록됨 (`src/pipeline/live_16step_flow.py`)
- **드라이버 교체 구조**: 지금은 로봇/저울 제어가 시뮬레이션으로 동작하지만, 실제 장치 코드가 준비되면 `register_action_driver()` 한 줄로 교체 가능하도록 설계됨

---

## 시작하기 (Getting Started)

이 레포를 처음 받았다면 아래 순서로 진행하면 됩니다.

1. 레포 클론 및 패키지 설치 (`pip install -r requirements.txt`, `pip install pyserial`)
2. `.env` 파일 생성 — MongoDB Atlas 접속 정보 입력
3. Prefect 서버 실행 — `python3 -m prefect server start`
4. `PREFECT_API_URL` 설정 — `python3 -m prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api`
5. 16단계 flow 실행 — `python3 -m src.pipeline.live_16step_flow`
6. Prefect 대시보드(`http://127.0.0.1:4200`)와 MongoDB Atlas 양쪽에서 결과 확인

패키지 설치 오류, `.env` 설정, Prefect 포트 문제 등 실제로 자주 발생하는 트러블슈팅까지 포함한 전체 과정은 아래 문서에 정리되어 있습니다.

> **MongoDB + Prefect 연결 전체 가이드**: [`docs/mongodb_prefect_setup.md`](docs/mongodb_prefect_setup.md)

---

## 프로젝트 구조

```
imms-sdl-os/
├── src/
│   ├── database/
│   │   ├── models.py              # Pydantic 모델 (Experiment/Task/Device/Sample, Action, Unit Operations)
│   │   └── mongo_client.py        # MongoDB 연결 및 저장/조회 함수
│   ├── hardware/
│   │   └── balance_mtsics.py      # XPR 저울 MT-SICS 드라이버
│   └── pipeline/
│       ├── action_driver.py       # 16단계 Action 실행 오케스트레이션 + 안전 검사
│       ├── dispense_command.py    # 범용 고체 분주 명령 인터페이스
│       ├── live_16step_flow.py    # Prefect + MongoDB 연동 16단계 flow
│       ├── ur3e_driver.py         # UR3e 로봇팔 + Robotiq 그리퍼 드라이버
│       └── zr_btc_synthesis_flow.py  # Zr-BTC MOF 합성 프로토콜 전체 실행 flow (57 Task)
├── data/
│   ├── schema/                    # MongoDB $jsonSchema validator
│   └── protocols/                 # 실험팀 제공 실제 프로토콜 (구조화된 JSON)
├── docs/                          # 설계 문서, 조사 노트, 진행 기록
│   ├── archive/                   # 이전 버전 문서 보존
│   └── images/                    # Prefect / MongoDB 실행 스크린샷
├── references/                    # 참고 논문 요약 (AlabOS, ChemOS 2.0)
└── tests/                         # 유닛 테스트 (pytest)
```

**현재 구현된 실험**: Zr-BTC MOF Synthesis Protocol (실험팀 제공) 기반 두 가지 flow
- `zr_btc_synthesis_flow.py` — 전체 프로토콜(Phase A~G, 57개 Task)을 순서대로 실행
- `live_16step_flow.py` — 그중 고체 분주(Solid Dosing) 16단계를 Prefect + MongoDB에 실제로 기록하며 실행, 안전장치(safety-critical 단계 차단) 포함

로봇팔(UR3e)과 저울(XPR) 제어는 현재 시뮬레이션 드라이버로 동작하며, 실제 하드웨어 연동은 진행 중입니다.

---

## 기술 스택

| 분야 | 기술 |
|------|------|
| 워크플로우 자동화 | [Prefect](https://www.prefect.io/) (`@flow` / `@task`, 로컬 서버 대시보드) |
| 데이터베이스 | MongoDB Atlas (클라우드), pymongo |
| 데이터 검증 | Pydantic |
| 언어 | Python 3.10+ |
| 로봇 제어 | UR3e RTDE Control/Receive Interface, Robotiq Gripper |
| 저울 통신 | Mettler Toledo XPR, MT-SICS 인터페이스, pyserial |
| 테스트 | pytest, mongomock |
| 참고 구조 | AlabOS, ChemOS 2.0 |

---

## 문서 가이드

`docs/` 안에 가이드를 넣어두었습니다. 무엇을 찾는지에 따라 아래를 참고하세요.

| 문서 | 내용 |
|------|------|
| [`docs/mongodb_prefect_setup.md`](docs/mongodb_prefect_setup.md) | MongoDB + Prefect를 처음부터 연결하는 전체 가이드 (트러블슈팅 포함) |
| [`docs/db_schema.md`](docs/db_schema.md) | MongoDB 컬렉션 스키마 설계 (Experiment/Task/Device/Sample) |
| [`docs/solid_dosing_workflow.md`](docs/solid_dosing_workflow.md) | 16단계 고체 분주(Solid Dosing) 워크플로우 정의 |
| [`docs/scheduler_interface.md`](docs/scheduler_interface.md) | 스케줄러 연동 인터페이스 계약 (`get_scheduler_job_queue` 등) |
| [`docs/multidose_integration.md`](docs/multidose_integration.md) | MultiDose 로봇/저울 실증 연동 인터페이스 계약 |
| [`docs/data_pipeline_and_error_handling.md`](docs/data_pipeline_and_error_handling.md) | 데이터 파이프라인 및 에러 처리 설계 |
| [`docs/precursor_catalog_and_run_metadata.md`](docs/precursor_catalog_and_run_metadata.md) | 전구체 카탈로그 및 실험 실행 메타데이터 스키마 |
| [`docs/live_execution_verification.md`](docs/live_execution_verification.md) | 16단계 flow 실제 실행 검증 기록 (스크린샷 포함) |
| [`docs/os_landscape.md`](docs/os_landscape.md) | 기존 SDL OS 사례 조사 (AlabOS, ChemOS 2.0 등) |
| [`docs/l2m3_notes.md`](docs/l2m3_notes.md) | L2M3 등 관련 문헌 추출 시스템 조사 노트 |
| [`docs/paper-notes.md`](docs/paper-notes.md) | 참고 논문 전체 정리 노트 |
| [`docs/progress.md`](docs/progress.md) | 주차별 연구 진행 기록 |
| `docs/archive/` | 이전 버전 스키마 문서 보존 |

---

## 핵심 참고 논문

| 논문 | 설명 |
|------|------|
| [AlabOS (Fei et al., 2024)](https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00129j) | Python 기반 재설정 가능한 워크플로우 관리 프레임워크 |
| [ChemOS 2.0 (Sim et al., 2024)](https://www.sciencedirect.com/science/article/pii/S2590238524001954) | 실험실을 OS로 보는 오케스트레이션 아키텍처 |
| [IvoryOS (2025)](https://www.nature.com/articles/s41467-025-60514-w) | Python SDL용 상호운용 가능한 자동 웹 인터페이스 |
| [UniLabOS (2025)](https://arxiv.org/abs/2512.21766) | AI-Native 자율실험실 OS |
| [Tom et al., Chem. Rev. 2024](https://pubs.acs.org/doi/full/10.1021/acs.chemrev.4c00055) | SDL 종합 리뷰 |

**추가 참고자료** (스키마 설계에 직접 반영, 자세한 내용은 [`docs/paper-notes.md`](docs/paper-notes.md)):
- OCTOPUS (Yoo et al., *Nat. Commun.* 2024) — 멀티유저 SDL 스케줄링, masking table 개념
- 지식그래프 기반 소재 합성 이론 리포트 — ActionGraph(DAG), Provenance 추적 개념

---

## 연구 진행 기록

진행 상황은 [`docs/progress.md`](docs/progress.md) 참고.

---
## 🔗 관련 기관

- [IMMS 공식 사이트][(https://sites.google.com/view/i-imms-2026)](https://imms.ewha.ac.kr/)
- [나종걸 교수 연구실](https://nagroup.ewha.ac.kr/)
- 이화여자대학교 화공신소재공학과
