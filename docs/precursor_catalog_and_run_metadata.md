# 🧪 물질 카탈로그(PrecursorCatalog) & Run 메타데이터 — 설계 문서

> 실험팀이 공유해준 두 자료(고체 전구체 리스트, Run 기록 시트)를 반영한 설계.
> 선배가 저번에 요청해둔 3가지 중 "①물질 리스트", "②결과 schema용 랩노트 샘플"에 해당.
> **이 문서는 설계만 다룬다. 코드는 확정 후 별도 구현.**

---

## 1. 왜 새 모델이 필요한가

지금 스키마의 `MaterialUsage`는 **"이번 Task에 실제로 뭘 얼마나 썼는지"**만 기록해요
(`material_name`, `target_mass_mg`, `actual_mass_mg` 등). 근데 실험팀이 보낸 표는
그것과는 다른 정보예요 — **"이 랩에 어떤 물질이 있고, 어디서 샀고, 어디에 보관돼
있는지"**를 담은 **재고 카탈로그**예요. 이 둘은 서로 다른 목적이라 별도 모델로
분리하는 게 맞아요:

| | 목적 | 언제 채워지나 |
|---|---|---|
| `PrecursorCatalog` (신규) | "이 물질이 뭔지, 어디 있는지" — 물질 자체의 정보 | 실험 전, 재고 등록 시 한 번 |
| `MaterialUsage` (기존) | "이번에 얼마나 썼는지" — 실행 결과 | 매 Task 실행마다 |

---

## 2. PrecursorCatalog — 물질 마스터 정보 (Image 1 기반)

### 표에서 확인된 필드

| 표 컬럼 | 의미 |
|---|---|
| `SolidPrecursorID` | 고유 ID (예: MSP0001) |
| `Name` | 물질명 (예: Zinc oxide) |
| `Notes` | 비고 |
| `CAS` | 화학물질 고유 등록번호 |
| `SMILES` | 분자 구조를 문자열로 표기 (있는 경우만) |
| `Formula` | 화학식 (예: ZnO) |
| `Vendor` | 구매처 (Sigma Aldrich 등) |
| `ReceivedDate` | 입고일 |
| `StorageLocation` | 보관 위치 (R1, D4-2 등) |
| `PackageScale` / `PackageUnit` | 구매 단위량 (예: 500 g) |

### 설계 초안

```python
class PrecursorCatalog(BaseModel):
    """
    실험실에 등록된 전구체(원료) 물질의 마스터 정보.
    MaterialUsage.material_name과 이름으로 연결되거나,
    나중에 precursor_id로 명시적 참조하도록 확장 가능.
    """
    precursor_id: str          # "MSP0001" — 표의 SolidPrecursorID 그대로
    name: str                  # "Zinc oxide"
    cas_number: Optional[str] = None
    smiles: Optional[str] = None
    formula: Optional[str] = None
    vendor: Optional[str] = None
    received_date: Optional[datetime] = None
    storage_location: Optional[str] = None
    package_scale: Optional[float] = None
    package_unit: Optional[str] = None      # "g", "mL" 등
    notes: Optional[str] = None
```

### MaterialUsage와의 연결 (결정 필요)

지금 `MaterialUsage.material_name`은 그냥 문자열이에요 ("ZrOCl2" 같은). 두 가지 방식 중 선택 필요:

- **방식 A (느슨한 연결)**: 이름으로만 매칭, `precursor_id`는 조회할 때 이름으로 `PrecursorCatalog`를 찾아서 확인. 구현 간단하지만 이름 오타 시 매칭 실패 위험.
- **방식 B (명시적 참조)**: `MaterialUsage`에 `precursor_id: Optional[str]` 필드를 추가해서, Task 생성 시점에 카탈로그의 정확한 ID를 참조. 더 안전하지만, Task를 만들 때마다 카탈로그 조회가 선행돼야 함.

→ **B를 추천**: 표에 이미 CAS 번호까지 있는 걸 보면 물질 관리를 꽤 엄밀하게 하고 있다는 뜻이라, 이름 매칭보다 ID 참조가 나중에 문제가 덜 생겨요.

---

## 3. Experiment 확장 — Run 메타데이터 (Image 2 기반)

### 표에서 확인된, 지금 스키마에 없는 필드

| 표 컬럼 | 지금 상태 | 비고 |
|---|---|---|
| `ExecutionMode` (Manual/Auto) | 없음 | **중요** — 아래 참고 |
| `SampleCount` | 없음 | 이 Run에서 몇 개 샘플을 만들었는지 |
| `ProjectDescription` | 없음 | 자유 텍스트 설명 (예: "Zn-BDC 4 pot synthesis") |

### 왜 `ExecutionMode`가 중요한가

지금까지 만든 스키마(Task, Action, Prefect flow, Device 락 등)는 전부 **"자동화 실행"**을 전제로 설계했어요. 근데 이 표를 보면 지금 실험팀은 **전부 Manual**로 실험하고 있어요 (`ExecutionMode` 컬럼이 전부 "Manual"). 즉:

- **지금 당장은** 자동화된 Task/Action 기록이 아니라, **사람이 손으로 한 실험 결과를 사후에 시스템에 입력**하는 흐름일 가능성이 높아요
- 이건 나쁜 게 아니라, **"Auto"와 "Manual" 실험을 같은 스키마로 함께 관리**해야 한다는 뜻이에요 — 자동화가 완성되기 전까지는 Manual 기록이 훨씬 많을 거예요

### 설계 초안

```python
class Experiment(BaseModel):
    # ...기존 필드들...
    execution_mode: Literal["manual", "auto"] = "manual"   # 신규
    sample_count: Optional[int] = None                      # 신규
    project_description: Optional[str] = None               # 신규
```

### Manual 실험은 Task/Action을 어떻게 기록할까 (열린 질문)

Auto 실험은 `build_solid_dosing_actions()`로 16단계가 자동 생성되지만, Manual 실험은 로봇이 안 움직이니 Action 시퀀스가 의미 없을 수 있어요. 두 가지 선택지:

- **선택지 1**: Manual 실험은 Task를 아주 간단하게만 기록 (예: `operation`, `material_usage`만 채우고 `actions`는 빈 리스트로 둠)
- **선택지 2**: Manual이어도 Action까지 기록하되, 각 Action의 시각(started_at/ended_at)을 사람이 나중에 손으로 입력

→ 이건 **선배·실험팀과 확인이 필요한 부분**이에요. 어느 쪽이든 지금 스키마(Task.actions가 선택적 필드)로 둘 다 커버 가능해서, 지금 코드를 바꿀 필요는 없어요.

---

## 4. 아직 결정 안 된 것 (구현 전 확인 필요)

1. **MaterialUsage ↔ PrecursorCatalog 연결 방식** (A vs B, 위 참고) — B 추천하지만 확인 필요
2. **RunStatus 값 이름 통일** — 표는 "Planned/Excuting(오타)/Completed", 지금 스키마는 "planned/running/completed/failed/held" — 매핑표 필요
3. **`SampleCount`가 `Sample` 컬렉션 문서 개수랑 항상 일치해야 하는지, 아니면 별도 집계값인지**
4. **Manual 실험의 Action 기록 방식** (위 참고)
5. **예진 임시 코드(H열)** — 표에 "나중에 삭제할 예정"이라고 적혀있어서, 지금 스키마에 반영 안 함 (임시 컬럼으로 판단)

---

## 5. 코드 구현 체크리스트 (다음 단계)

- [x] `PrecursorCatalog` Pydantic 모델 추가
- [x] `Experiment.execution_mode`, `sample_count`, `project_description` 필드 추가
- [x] `MaterialUsage.precursor_id` 필드 추가 (방식 B 채택)
- [x] `mongo_client.py`에 `precursor_catalog` 컬렉션 저장/조회 함수
      (`register_precursor`, `get_precursor`, `find_precursor_by_name`)
- [x] 테스트 10개 작성 (`tests/test_precursor_catalog.py`) — 전체 테스트 77개 통과
- [ ] RunStatus 값 매핑 확정 후 반영 (표: Planned/Excuting/Completed ↔ 스키마: planned/running/completed/failed/held)
- [ ] Manual 실험의 Action 기록 방식 확정 (선배·실험팀 확인 필요)
