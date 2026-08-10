---

## MOF 실험 데이터 스키마 정리

![MOF 실험 데이터 스키마 구조도](images/mof_experiment_schema_diagram)

### 4단계 계층

```
Experiment (실험 캠페인)
    └── Task (개별 합성 단계, 예: "고체 분주 1회")
            ├── Device (어떤 장비를 썼는지)
            ├── MaterialUsage (어떤 물질을, 목표/실제 얼마나 썼는지)
            └── Sample (이 Task가 만들어낸 결과물)
```

### 1. Experiment — 실험 캠페인 단위

하나의 MOF 합성 실험 전체(예: "Zr-BTC MOF 합성")를 담는 최상위 단위 시용.

| 필드 | 내용 |
|---|---|
| `name`, `target_material` | 실험 이름, 목표 물질 (예: Zr-BTC MOF) |
| `reagents` | 계획된 시약 목록 (metal/ligand/solvent, 계획 용량) |
| `phase_sequence` | 합성 공정 단계 순서 (A~G) |
| `status` | planned/running/completed/failed |

### 2. Task — 실험의 개별 단계

Experiment 안의 세부 단계 하나 (예: "고체 분주", "가열", "원심분리"). 실제 프로토콜의 19종 오퍼레이션(Unit Operation)에 대응됨.

**중요 — 고체 분주는 더 세분화되어 있음:**
고체 분주 Task 하나는 내부적으로 **16단계 세부 동작**(로봇팔이 헤드 집기 → 저울 장착 → 도징 → 원위치 등)으로 다시 쪼개져서 기록됨. 
-> 따라서, "정확히 어느 단계에서 문제가 생겼는지"까지 추적 가능하게 설계.

### 3. MaterialUsage — 물질 사용 기록 

Task 하나가 어떤 물질을 얼마나 썼는지 정확히 기록하는 스키마.

| 필드 | 내용 |
|---|---|
| `material_name` | 예: ZrOCl2, BTC(리간드) |
| `role` | metal / ligand / solvent / modulator 중 하나로 분류 |
| `concentration` | 농도 |
| `target_mass_mg` | 목표 분주량 (계산으로 미리 정한 값) |
| `actual_mass_mg` | 실제로 분주된 양 (저울이 측정한 실측값) |
| `error_rate_pct` | 목표 대비 오차율 — 자동 계산 |

**중요한 이유**: 실험이 자동화로 진행돼도, "이 배치에 실제로 몇 mg이 들어갔는지"가 정확히 남음.
-> 목표치가 아니라 **실측값 기준**으로 기록되기 때문에, 나중에 물성 데이터(수율, 결정 크기 등)를 분석할 때 "정확히 어떤 조성으로 만들어진 샘플인지" 역추적이 가능함.

### 4. Sample — 산출물

각 Task가 만들어낸 결과물(용액, 슬러리, 최종 결정 등). 예: `metal_sol`, `rxn_mixture`, `MOF_slurry`, `xrd_result_final`

**추적 가능한 것**: `input_refs`/`output_refs`로 "이 샘플이 어떤 재료로부터, 어떤 Task를 거쳐 만들어졌는지" 체인을 따라 역추적할 수 있음.
-> 예를 들어 최종 XRD 결과가 이상하게 나왔을 때, 그 샘플이 정확히 몇 mg의 어떤 시약으로 만들어졌는지까지 거슬러 올라갈 수 있다.

### 5. Device / DosingHead — 장비 및 소모품 관리

- **Device**: 어떤 장비(로봇팔, 저울)를 썼는지, 지금 사용 가능한지
- **DosingHead**: 물질별로 배정된 도징헤드 재고 관리 (어떤 헤드에 어떤 물질이 로드되어 있는지)

