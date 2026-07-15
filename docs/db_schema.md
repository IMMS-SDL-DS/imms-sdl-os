# 🗄️ MOF 실험 DB 스키마 설계 (v2)

> v1(초기 일반 초안)은 AlabOS/ChemOS 2.0 구조만 참고한 추측 기반 설계였음.
> v2는 실험팀이 공유해준 **실제 프로토콜**(`MOF_실험_공정팀_final.pdf`, Zr-BTC MOF Synthesis, 26.01.28~29)을
> 그대로 반영해서 다시 짠 버전. v1 문서는 [`docs/archive/db_schema_v1.md`](archive/db_schema_v1.md)에 보존.

---

## 설계 근거

1. **OCTOPUS** (Yoo et al., *Nat. Commun.* 2024) — Platform > Module > Task > Action 계층,
   장비별 masking table로 충돌 방지 → `Device.shared_phases`, `Task.required_device_type()`
2. **ActionGraph** (arXiv 2512.02947) — 합성 레시피를 DAG로 표현.
   Node = 물질/조건/장치, Edge = Association(조작↔대상) + Reference(이전 output → 다음 input)
   → `Task.input_refs` / `Task.output_refs`
3. **실험팀 프로토콜** §4 Unit Operation Schema (OP-01~OP-19), §5 Variable Schema
   → `src/database/models.py`의 `OperationType` enum + operation별 Pydantic 파라미터 모델로 그대로 이식

실제 데이터는 `data/protocols/zr_btc_mof_protocol.json`에, 파이썬 모델은
`src/database/models.py`에, 이를 실행하는 Prefect flow는
`src/pipeline/zr_btc_synthesis_flow.py`에 있음.

---

## 4개 핵심 컬렉션

### 1. `experiment` — 실험 캠페인 단위

```python
{
    "experiment_id": "exp_zrbtc_001",
    "name": "Zr-BTC MOF Synthesis",
    "protocol_version": "26.01.28~26.01.29",
    "target_material": "Zr-BTC MOF",
    "researcher": "손시영",
    "status": "planned | running | completed | failed | held",
    "reagents": [
        { "name": "ZrOCl2", "role": "Metal Source", "amount": "97 mg",
          "dispense_device": "Solid Dispenser", "notes": "산화 주의, Desiccator 보관" }
    ],
    "phase_sequence": ["A", "B", "C", "D", "E", "F", "G"],
    "notes": ["Phase D-1: 혼합 순서(L→M) 반드시 준수 — 역순 시 부산물 생성"]
}
```

### 2. `task` — 프로토콜의 개별 Step 1개 (예: "D-1")

```python
{
    "task_id": "exp_zrbtc_001_D-1",
    "experiment_id": "exp_zrbtc_001",
    "phase": "D",
    "step_code": "D-1",
    "operation": "TRANSFER",
    "parameters": { "source": "ligand_sol", "dest": "metal_sol",
                     "volume_ml": None, "order_critical": True },
    "device_id": "dev_opentron_flex",
    "input_refs": ["sample_ligand_sol", "sample_metal_sol"],
    "output_refs": ["sample_rxn_mixture"],
    "order_critical": True,
    "status": "pending | running | success | failed | held",
    "actual_values": {},
    "prefect_task_run_id": None
}
```

**Task ↔ Module/Phase 매핑**: OCTOPUS 논문에서 헷갈렸던 "Task 컬렉션이 Module 단위인지 Task 단위인지" 문제는
실제 프로토콜을 보니 명확해짐 — **Phase(A~G) = OCTOPUS의 Module, Step(A-1, B-2...) = OCTOPUS의 Task**.
`Task.phase` 필드로 이 계층을 표현.

**Unit Operation 목록** (OP-01~OP-19, `src/database/models.py`의 `OperationType`):

| OP ID | Operation | 필요 장비 타입 |
|---|---|---|
| OP-01 | DISPENSE_SOLID | solid_dispenser |
| OP-02 | VERIFY_MASS | balance |
| OP-03 | DISPENSE | liquid_handler |
| OP-04 | TRANSFER | liquid_handler |
| OP-05 | DECANT | liquid_handler/manual |
| OP-06 | MIX | liquid_handler |
| OP-07 | SONICATE | sonicator |
| OP-08 | CENTRIFUGE | centrifuge |
| OP-09 | VORTEX | vortex_mixer |
| OP-10 | BALANCE_CHECK | balance |
| OP-11 | SEAL | manual |
| OP-12 | HEAT | heater |
| OP-13 | DRY | manual |
| OP-14 | SAMPLE | manual |
| OP-15 | ANALYZE_XRD | xrd |
| OP-16 | REPEAT | - |
| OP-17 | SOLVENT_CHANGE | liquid_handler |
| OP-18 | GRIND | manual |
| OP-19 | ANALYZE_OM | optical_microscope |

### 3. `device` — 연결된 장비

```python
{
    "device_id": "dev_opentron_flex",
    "name": "Opentron Flex",
    "device_type": "liquid_handler",
    "connection": "python_api",
    "shared_phases": ["A", "B", "C", "D", "F", "G"],
    "status": "idle | busy | offline | maintenance",
    "last_used_at": None
}
```

> Opentron Flex가 Phase A~D, F, G에 걸쳐 반복 사용됨 (DISPENSE, TRANSFER, MIX, DECANT, SOLVENT_CHANGE).
> 여러 실험을 병렬로 돌릴 경우 이 장비를 쓰는 Task끼리는 반드시 직렬화해야 함 (OCTOPUS의 masking table 개념).

### 4. `sample` — 중간/최종 산출물

```python
{
    "sample_id": "sample_rxn_mixture",
    "experiment_id": "exp_zrbtc_001",
    "sample_code": "rxn_mixture",
    "sample_type": "solution | slurry | solid | xrd_data | om_data",
    "produced_by_task_id": "exp_zrbtc_001_D-1",
    "consumed_by_task_ids": ["exp_zrbtc_001_D-2"],
    "properties": {}
}
```

sample_code 예시: `homo_solution`, `metal_sol`, `ligand_sol`, `rxn_mixture`, `MOF_slurry`,
`xrd_result_1`, `dmf_washed`, `washed_MOF`, `xrd_result_final`

---

## 관계도 (ActionGraph 스타일 DAG)

```
Experiment
    └── Task (Phase A~G, Step 단위)
            ├── Device        (N:1, required_device_type()로 검증)
            ├── input_refs  → Sample (이전 Task의 output)     ─┐
            └── output_refs → Sample (이 Task의 산출물)        ├─ Reference Edge
                                                                 ┘
```

예: `D-1 TRANSFER` → input: `ligand_sol`, `metal_sol` / output: `rxn_mixture`
→ `D-3 HEAT` → input: `rxn_mixture` / output: `MOF_slurry`
→ `E-1 SAMPLE` → input: `MOF_slurry` / output: (XRD holder로 이동)

---

## 실전 반영 사항 (v1 → v2 변경 이유)

| 항목 | v1 (추측 기반) | v2 (실제 프로토콜 기반) |
|---|---|---|
| Task 단위 | 불명확 (Module인지 Step인지) | Phase=Module, Step=Task로 명확화 |
| Parameter 검증 | 자유 dict | Operation별 Pydantic 모델 (`OPERATION_PARAM_MODEL`) |
| 순서 제약 | 없음 | `order_critical` 필드 (D-1 TRANSFER 순서 위반 방지) |
| 반복 처리 | 없음 | `REPEAT` operation + `repeat_of` 필드 (Washing 3회 반복) |
| Sample 흐름 추적 | 없음 | `input_refs`/`output_refs`로 Reference Edge 표현 |
| Device 공유 문제 | 없음 | `shared_phases`로 Opentron Flex 등 공유 장비 명시 |

---

## 재시도(Retry) 안전 정책

Prefect의 `retries`는 통신 에러 등으로 Task가 실패했을 때 자동으로 다시 실행해주지만,
**물리적 부작용이 있는 오퍼레이션**을 무조건 재시도하면 위험하다. 예를 들어
`DISPENSE_SOLID`가 "실패"로 기록됐다가 재시도됐는데, 사실은 통신 에러가 아니라
이미 절반쯤 분주된 상태였다면 목표량의 2배가 들어갈 수 있다.

그래서 `src/database/models.py`의 `SAFE_TO_RETRY_OPERATIONS`로 오퍼레이션을 분류한다:

| 분류 | Operation | 이유 |
|---|---|---|
| ✅ 안전 (재시도 허용) | VERIFY_MASS, ANALYZE_XRD, ANALYZE_OM, BALANCE_CHECK | 측정/판독만 하고 물질 상태를 바꾸지 않음 |
| ⚠️ 위험 (재시도 금지) | DISPENSE_SOLID, TRANSFER, HEAT, CENTRIFUGE 등 나머지 전부 | 이미 일부 실행됐을 가능성이 있어 재시도 시 물리적 사고 위험 |

`src/pipeline/zr_btc_synthesis_flow.py`의 `execute_step` task는 기본값 `retries=0`이고,
`_call_execute_step()` 헬퍼가 `is_safely_retryable(operation)`을 체크해서 안전한
오퍼레이션에만 `.with_options(retries=1)`로 재시도를 허용한다.

## TODO
- [x] Unit Operation Schema를 Pydantic 모델로 구현 (`src/database/models.py`)
- [x] 실제 프로토콜을 JSON 데이터로 구조화 (`data/protocols/zr_btc_mof_protocol.json`)
- [x] Prefect flow로 전체 프로토콜 실행 테스트 (`src/pipeline/zr_btc_synthesis_flow.py`, 시뮬레이션 모드)
- [x] MongoDB Atlas 연결 (`src/database/mongo_client.py`) — `.env` 설정 후 실제 저장 확인
- [x] DISPENSE_SOLID 등 물리적 오퍼레이션의 안전한 재시도 정책 구현 (`SAFE_TO_RETRY_OPERATIONS`)
- [ ] 실제 장비 Python API 연결 (`execute_step()` 안의 `[SIM]` 부분 교체)
- [ ] Device 상태(idle/busy) 실시간 갱신 → 여러 실험 병렬 실행 시 충돌 방지 로직
- [ ] XRD 파일 자동 파싱 후 `sample.properties`에 저장

### MongoDB 연결 사용법
```bash
cp .env.example .env
# .env 열어서 MONGODB_URI, MONGODB_DB_NAME 채우기 (Atlas Connect 화면에서 복사)

python -m src.database.mongo_client        # 연결 테스트 + 컬렉션/인덱스 생성
python -m src.pipeline.zr_btc_synthesis_flow  # 실제 DB에 저장하며 프로토콜 실행
```
`.env`가 없거나 연결에 실패해도 flow 자체는 시뮬레이션 모드로 계속 진행됩니다 (`save_to_db=False`로 명시적으로 끌 수도 있음).
