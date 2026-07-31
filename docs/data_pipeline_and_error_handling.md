# 🔌 데이터 파이프라인 & 예외 처리 설계 — State/Event/Metadata, Task 연동, 에러 처리

> 선배 추가 요청(2026.7) 3가지를 다룬다. `docs/solid_dosing_workflow.md`(Action 레벨
> 모델)의 후속 설계 문서. **코드는 여기서 안 짬 — 구조만 설계.**
>
> 선배가 실험팀에 요청해둔 3가지(결과 엑셀/랩노트, material 리스트, 오차 허용범위)는
> 아직 안 왔으므로, 정확한 숫자값은 나중에 채우고 지금은 그 값이 들어갈 "자리"만
> 스키마에 미리 만들어둔다.

---

## 1. 물리적 동작의 데이터 entity화

### 1-1. State Data (신규 — `DeviceState`)

지금 `Device` 모델은 `status: idle/busy/offline/maintenance`만 있음 — 이건 "이 장비를
지금 다른 Task가 쓰고 있는지"만 나타내는 락(lock)용 상태고, 선배가 요청한 **실시간
물리 상태**(문 개폐, 저울 값, 안전센서)는 전혀 다른 개념. 별도 모델로 분리:

```python
class DeviceState(BaseModel):
    """장비의 실시간 물리 상태. Device(락 상태)와는 별개 — 매 순간 갱신되는 텔레메트리."""
    device_id: str
    door_status: Optional[Literal["open", "closed"]] = None
    current_reading_mg: Optional[float] = None   # 저울이 지금 보여주는 값
    is_stable: Optional[bool] = None              # 값이 안정화됐는지 (§3-1 참고)
    safety_sensor_active: Optional[bool] = None
    recorded_at: datetime
```

**저장 방식 결정**: 이건 "매 순간 계속 바뀌는 값"이라 Task/Sample처럼 영구 기록이라기보다
**최신 상태 스냅샷**에 가까움. `device_state` 컬렉션에 `device_id`를 키로 upsert하는
방식 추천 (매번 새 문서 안 만들고 덮어쓰기) — 이력이 필요하면 나중에 별도 `device_state_log`
컬렉션으로 확장 가능.

### 1-2. Event Log (기존 `Action` 모델을 그대로 사용)

선배가 예시로 든 "저울 문 열림", "도징 시작", "바이알 이동 완료"는 **이미 만든
`ActionType`과 1:1로 매핑됨**:

| 선배 예시 | 기존 ActionType |
|---|---|
| 저울 문 열림 | `DOOR_OPEN` |
| 도징 시작 | `DOSE` |
| 바이알 이동 완료 | `PLACE` (vial) |

`Action.started_at`/`ended_at`/`status`가 정확히 "정확한 타임스탬프 + 성공/실패"를
이미 충족함. **새로 만들 것 없음** — 이미 있는 걸 그대로 쓰면 됨.

### 1-3. Metadata (기존 `MaterialUsage`에 오차율 필드만 추가)

```python
class MaterialUsage(BaseModel):
    material_name: str
    role: MaterialRole
    concentration: Optional[float] = None
    concentration_unit: Optional[str] = None
    target_mass_mg: float
    actual_mass_mg: Optional[float] = None
    head_id: Optional[str] = None
    vial_id: Optional[str] = None

    error_rate_pct: Optional[float] = None   # ← 신규: (actual - target) / target * 100
    # actual_mass_mg가 채워지는 시점에 자동 계산해서 같이 저장 (계산 로직은 코드 단계에서)
```

---

## 2. 워크플로우 간 데이터 연동 규격화 (신규 설계)

### 문제 정의
지금까지는 Task 하나(예: DISPENSE_SOLID)가 끝나면 그걸로 끝이었음. 근데 실제 파이프라인은
**고체 분주 Task의 결과(Actual)가 다음 Task(액체 분주)의 입력 계산에 영향을 줘야 함**
(예: 고체가 목표보다 적게 들어갔으면, 액체 분주량도 그에 맞춰 비례 조정해야 농도가 맞음).

### 설계: `TaskHandoff` — Task 사이를 흐르는 표준 데이터 봉투

```python
class TaskHandoff(BaseModel):
    """
    Prefect Task 함수가 다음 Task 함수에게 넘겨주는 표준 데이터 형식.
    MongoDB 저장용 스키마(Task)와는 별개 — 이건 "메모리 상에서 Task 간 전달되는 값".
    """
    source_task_id: str
    status: Literal["success", "failed", "held"]
    output_sample_ids: list[str] = []
    material_usage: Optional[MaterialUsage] = None   # actual_mass_mg 포함
    actual_values: dict[str, Any] = {}
    errors: list["ErrorRecord"] = []                  # §3-3 참고
```

### 흐름 예시 (고체 분주 → 액체 분주)

```python
# Prefect flow 안에서:
solid_result: TaskHandoff = run_dispense_solid_task(...)

# 다음 Task는 solid_result.material_usage.actual_mass_mg를 받아서
# 목표 농도를 유지하기 위한 액체(용매) 투입량을 재계산
liquid_result: TaskHandoff = run_dispense_liquid_task(
    target_concentration=0.5,
    actual_solid_mass_mg=solid_result.material_usage.actual_mass_mg,  # ← 여기서 연결
    ...
)
```

**핵심**: `target`은 사전에 코드가 계산해서 장비에 내리는 명령이고, `actual`은 장비가
실행한 뒤 나온 결과. 이 둘이 다를 수 있다는 걸 항상 전제하고, **다음 Task는 target이
아니라 actual을 기준으로 재계산**하는 게 원칙.

### 최종 로그 통합
`Experiment` 문서 또는 별도 `pipeline_run` 문서에, 그 Experiment에 속한 모든 Task의
`TaskHandoff` 결과를 순서대로 모아서 최종 요약을 만들 수 있음 (지금 `Task.input_refs`/
`output_refs`로 이미 체인이 연결되어 있으므로, 이 체인을 따라가며 조립하는 함수로 구현
가능 — 코드 단계에서 `get_pipeline_summary(experiment_id)` 같은 함수로).

---

## 3. 예외 처리 및 피드백 루프

### 3-1. 안정화 대기 로직 (신규 ActionType: `STABILIZE`)

로봇이 바이알을 놓거나 도징이 끝난 직후, 저울 값이 흔들리다가 안정되는 구간이 있음.
이걸 별도 Action으로 명시적으로 넣어야 함 — 지금 13단계 시퀀스에 없던 단계:

```python
# ActionType에 추가
STABILIZE = "STABILIZE"   # 저울 값이 안정화될 때까지 대기

class StabilizeParams(BaseModel):
    stability_threshold_mg: float   # 이 범위 안에서 변화가 없어야 "안정"으로 판단 (예: ±0.1mg)
    max_wait_sec: float             # 이 시간 넘으면 타임아웃 에러
```

**시퀀스에 삽입할 위치**: PLACE(5번) 이후, DOSE(8번) 이전에 한 번, 그리고 DOSE(8번) 이후
DOOR_OPEN(9번) 이전에 한 번 더 — 즉 "무게를 재려는 시점 직전마다" 삽입. 13단계 시퀀스가
15단계로 늘어남 (STABILIZE 2회 추가).

**타임아웃 시**: `ErrorCategory.STABILIZATION_TIMEOUT`으로 기록 (§3-3), Task는 `failed`
처리.

### 3-2. 오차 범위 대응 (신규: `ToleranceDecision`)

```python
class ToleranceDecision(str, Enum):
    WITHIN_TOLERANCE = "within_tolerance"   # 정상, 다음 단계 진행
    CORRECTION_DOSE = "correction_dose"     # 부족분만큼 추가 도징 시도
    FAIL_VIAL = "fail_vial"                 # 이 바이알은 포기, Task를 failed로 기록
```

**판단 로직 초안** (정확한 tolerance_mg 값은 실험팀 데이터 도착 후 확정):
```
error = actual_mass_mg - target_mass_mg
if abs(error) <= tolerance_mg:
    → WITHIN_TOLERANCE
elif error < 0 and correction_attempts < MAX_CORRECTION_ATTEMPTS:
    → CORRECTION_DOSE  (부족한 만큼 추가 DOSE Action을 새로 만들어 실행)
else:
    → FAIL_VIAL
```

**주의**: `CORRECTION_DOSE`는 지난번 만든 "재시도 금지 원칙"(`SAFE_TO_RETRY_OPERATIONS`)과
다른 개념. 그건 "통신 에러로 실패했을 때 똑같은 명령을 무작정 다시 보내는 것"이 위험하다는
거였고, 이건 **"측정 결과를 보고 판단해서 명시적으로 새로운 보정 Action을 만드는 것"**이라
안전함 (얼마나 부족한지 알고 그만큼만 추가하는 거니까). 다만 **무한 루프 방지를 위해
`MAX_CORRECTION_ATTEMPTS`로 횟수 제한 필수**.

### 3-3. 에러 로깅 스키마 (신규: `ErrorRecord`)

```python
class ErrorCategory(str, Enum):
    COMMUNICATION = "communication"                # 장비 통신 오류
    TARGET_NOT_REACHED = "target_not_reached"       # 목표 무게 도달 실패 (보정 한도 초과)
    SAFETY_VIOLATION = "safety_violation"           # 안전 순서 위반 (RETRACT 실패 등, §기존)
    STABILIZATION_TIMEOUT = "stabilization_timeout"  # §3-1
    UNKNOWN = "unknown"

class ErrorRecord(BaseModel):
    error_id: str
    task_id: str
    action_id: Optional[str] = None    # 어느 Action에서 발생했는지 (있으면)
    category: ErrorCategory
    message: str
    occurred_at: datetime
```

`Task.errors: list[ErrorRecord] = []` 필드로 Task에 부착. 하나의 Task 실행 중 여러
에러가 날 수도 있으므로 리스트로.

---

## 4. 선배가 기다리는 실험팀 자료 → 스키마 연결 지점

| 실험팀에서 받을 자료 | 들어갈 자리 |
|---|---|
| 결과 엑셀/랩노트 샘플 | `Sample.properties`(자유 필드) 구조를 이 샘플에 맞춰 구체화. 실제 필드명 확정 |
| Metal/Ligand/용매 리스트 | `MaterialRole`에 이미 METAL/LIGAND/SOLVENT/MODULATOR 있음 — 리스트 받으면 각 물질을 이 role로 분류만 하면 됨 |
| 정량 오차 허용범위 | `DispenseSolidParams.tolerance_mg`(이미 있음!) 값을 실제 숫자로 채우고, §3-2 `ToleranceDecision` 판단 로직의 임계값으로 사용 |

**좋은 소식**: `tolerance_mg`는 처음부터 있던 필드라 새로 안 만들어도 됨 — 숫자만 나중에
채우면 됨.

---

## 5. 종합: 새로 필요한 모델 목록 (코드 구현 시 체크리스트)

- [x] `DeviceState` — 실시간 State Data (§1-1)
- [x] `MaterialUsage.error_rate_pct` 필드 + `compute_error_rate()` 메서드 (§1-3)
- [x] `TaskHandoff` — Task 간 데이터 연동 표준 봉투, `TaskHandoff.from_task()` 헬퍼 (§2)
- [x] `ActionType.STABILIZE` + `StabilizeParams`, 시퀀스에 2곳 삽입 (13→15단계) (§3-1)
- [x] `ToleranceDecision` enum + `decide_tolerance()` 판단 함수 (§3-2)
- [x] `ErrorCategory` enum + `ErrorRecord` 모델, `Task.errors` 필드 (§3-3)
- [x] `get_pipeline_summary(db, experiment_id)` — Task들을 모아 최종 로그 요약 조립 (§2)
- [x] `save_device_state()` / `get_device_state()` — DeviceState 저장/조회 (§1-1)
- [x] 테스트 16개 추가 (`test_solid_dosing_actions.py` 확장 + `test_pipeline_summary.py` 신설)
      — 전체 테스트 44개 전부 통과

**보류 중** (실험팀 자료 도착 후 확정): `tolerance_mg` 실제 값, `stability_threshold_mg`
실제 값, `Sample.properties` 세부 필드명. 지금은 기본값(`stability_threshold_mg=0.1`,
`max_wait_sec=30.0`)으로 임시 설정해둠 — 실제 값 오면 교체 필요.
