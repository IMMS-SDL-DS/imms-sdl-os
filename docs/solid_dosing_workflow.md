# 🧪 고체 분주(Solid Dosing) 워크플로우 — 설계 문서

> 지금까지 만든 `DISPENSE_SOLID`는 Task 레벨의 큰 덩어리였는데,
> 실제 MultiDose 로봇팔+저울은 그 안에서 12단계로 세분화된 동작을 거친다.
> 이걸 각각 함수화(Unit Operation의 하위 단위 = "Action")하고, 동시에
> 어떤 물질을 얼마나 썼는지(material/concentration/amount)를 추적하는 데이터
> 관리까지 필요하다
>
> **이 문서는 설계만 다룸 -> 코드는 이 설계가 확정된 뒤 별도로 구현.**

---

## 1. 지금 스키마와 뭐가 다른지

기존 `DISPENSE_SOLID`(OP-01)는 이렇게 하나의 Task였음:
```
Task(operation=DISPENSE_SOLID, parameters={reagent, mass_mg, tolerance_mg, vessel})
```

이제 이 Task **안에** 로봇팔·저울의 개별 동작(Action)이 순서대로 12번 있고,
각각이 독립적으로 성공/실패할 수 있는 단위라는 것. OCTOPUS 논문 용어로 치면:

```
Platform > Module > Task > Action
                     └─ DISPENSE_SOLID (지금까지 만든 것)
                          └─ 12개 Action (이번에 새로 설계할 것)
```

---

## 2. Action 레벨 데이터 모델 — 재사용 가능한 타입으로 일반화

제공된 12단계를 그대로 12개의 서로 다른 타입으로 만들면 재사용이 안 됨.
공통 패턴을 뽑아서 **7개의 재사용 가능한 ActionType**으로 일반화:

| ActionType | 설명 | 실행 주체 |
|---|---|---|
| `PICK` | 로봇팔이 물체(헤드/바이알)를 집음 | 로봇팔 |
| `PLACE` | 로봇팔이 물체를 내려놓음 | 로봇팔 |
| `MOUNT` | 헤드를 저울에 장착 | 로봇팔 |
| `RETRACT` | 로봇팔이 작업 공간 밖으로 빠져나감 | 로봇팔 |
| `DOOR_OPEN` | 저울 문 열기 | 저울 |
| `DOOR_CLOSE` | 저울 문 닫기 | 저울 |
| `DOSE` | 설정량만큼 실제 계량 분주 | 저울+헤드 |

### 구체적인 12단계 → Action 시퀀스 매핑

| # | 설명 | ActionType | object_ref | 안전 제약 |
|---|---|---|---|---|
| 1 | 헤드 판에서 헤드 꺼냄 | `PICK` | head | - |
| 2 | 저울에 헤드 장착 | `MOUNT` | head → balance | - |
| 3 | 바이알 랙에서 바이알 잡음 | `PICK` | vial | - |
| 4 | 저울 문 열림 | `DOOR_OPEN` | - | - |
| 5 | 바이알을 저울 중앙에 놓음 | `PLACE` | vial → balance_center | - |
| 6 | 로봇팔 빠짐 → 문 닫힘 | `RETRACT` + `DOOR_CLOSE` | - | ⚠️ **RETRACT가 DOOR_CLOSE보다 반드시 먼저** (안 그러면 문이 로봇팔에 충돌) |
| 7 | 설정량 도징 | `DOSE` | material | ⚠️ 재시도 금지 대상 (물리적 부작용, 기존 `SAFE_TO_RETRY_OPERATIONS` 정책과 동일 원칙) |
| 8 | 저울 문 열림 | `DOOR_OPEN` | - | - |
| 9 | 바이알 꺼냄 | `PICK` | vial ← balance_center | - |
| 10 | 문 닫힘 | `DOOR_CLOSE` | - | - |
| 11 | 바이알 원위치 | `PLACE` | vial → vial_rack | - |
| 12 | 헤드 원위치 | `PLACE` | head → head_rack | - |

**13개 레코드**가 됨 (6번이 RETRACT+DOOR_CLOSE 두 개로 쪼개지므로).

### Action 모델 초안 (Pydantic, 실제 구현 시 `models.py`에 추가 예정)

```python
class ActionType(str, Enum):
    PICK = "PICK"
    PLACE = "PLACE"
    MOUNT = "MOUNT"
    RETRACT = "RETRACT"
    DOOR_OPEN = "DOOR_OPEN"
    DOOR_CLOSE = "DOOR_CLOSE"
    DOSE = "DOSE"

class Action(BaseModel):
    action_id: str
    parent_task_id: str          # 이 Action이 속한 DISPENSE_SOLID Task
    sequence_index: int          # 1~13, 실행 순서
    action_type: ActionType
    object_ref: Optional[str]    # "head_ZrOCl2", "vial_003" 등 대상 물체
    source_location: Optional[str]
    dest_location: Optional[str]
    status: Literal["pending","running","success","failed"] = "pending"
    safety_critical: bool = False  # True면 이전 Action이 반드시 성공해야 진행
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
```

**왜 Task와 별도 모델로 분리하는가**: Task(DISPENSE_SOLID)는 여전히 "한 번의 분주
이벤트"라는 상위 단위로 유지하고, Action은 그 내부의 세부 실행 로그로 둠. 이러면
스케줄러(Mehdi)나 Sample 추적 로직은 지금처럼 Task 단위로만 보면 되고, Action은
"디버깅/장비 제어용 세부 로그"로 필요할 때만 들여다보는 구조가 됨 — 기존 스키마를
갈아엎지 않고 확장 가능.

---

## 3. Material 추적 데이터 모델

2번째 부분: metal/ligand/solvent 같은 물질 정보, 농도, 실제 사용량을
자동화 실행 중 추적하고 실험 종료 후에도 기록이 남아야 함.

### 지금 스키마의 한계
- `Experiment.reagents`(`ReagentSpec`)는 프로토콜 **설계 단계의 계획값**만 있음
  (예: "ZrOCl2, 97mg 예정") — 실제 실행 중 매 배치마다 달라질 수 있는 값이 아님
- `Task.actual_values`는 자유 dict라 저장은 되지만, 농도(concentration) 개념이 없고
  구조화되어 있지 않아 나중에 "이 캠페인에서 총 몇 mg의 ZrOCl2를 썼는지" 같은 집계가 어려움

### MaterialUsage 모델 초안

```python
class MaterialRole(str, Enum):
    METAL = "metal"
    LIGAND = "ligand"
    SOLVENT = "solvent"
    MODULATOR = "modulator"

class MaterialUsage(BaseModel):
    material_name: str            # "ZrOCl2"
    role: MaterialRole
    concentration: Optional[float] = None
    concentration_unit: Optional[str] = None  # "M", "mg/mL" 등
    target_mass_mg: float
    actual_mass_mg: Optional[float] = None    # VERIFY_MASS 결과로 채워짐
    head_id: Optional[str] = None             # 어느 도징헤드 카트리지를 썼는지
    vial_id: Optional[str] = None
```

**Task와의 관계**: `DISPENSE_SOLID` Task 하나당 `MaterialUsage` 하나가 자연스럽게
1:1로 붙음 (Task에 `material_usage: Optional[MaterialUsage]` 필드 추가).

**Sample과의 관계**: Sample이 최종적으로 "이 샘플은 어떤 재료들로 만들어졌는지"
알아야 하므로, 기존 `input_refs`(Reference Edge)를 통해 관련 Task들을 따라가면
각 Task의 `material_usage`를 모아서 전체 조성(recipe)을 재구성할 수 있음 —
새 필드를 안 늘리고 기존 Reference Edge 구조를 그대로 활용.

---

## 4. 안전/순서 제약 — 기존 정책과의 연결

- **DOSE(7번)는 기존 `SAFE_TO_RETRY_OPERATIONS`에 속하지 않는 대상**으로 취급 —
  물리적 부작용이 있으므로 재시도 금지 원칙을 Action 레벨에도 그대로 적용해야 함
- **RETRACT → DOOR_CLOSE 순서**는 새로운 형태의 `order_critical` — 지금까지는
  "TRANSFER 순서(L→M)"처럼 물질 흐름 순서였는데, 이번엔 **물리적 충돌 방지**를 위한
  순서 제약이라는 점에서 새로운 카테고리. `Action.safety_critical` 필드로 표현

---

## 5. 아직 결정 안 된 것 (구현 전 확인 필요)

1. **Action을 별도 MongoDB 컬렉션으로 둘지, Task 문서 안에 embedded list로 둘지**
   — 컬렉션 분리 시 조회는 유연하지만 조인 필요, embedded 시 조회는 간단하지만
   Task 문서가 커짐. Action 개수가 Task당 최대 13개 정도로 적으니 **embedded 방식
   추천** (별도 컬렉션 안 만들고 `Task.actions: list[Action]`)
2. **DOSE Action의 material 파라미터를 Task의 MaterialUsage와 어떻게 안 겹치게
   연결할지** — 중복 저장 방지 필요
3. **로봇 드라이버 인터페이스(`RobotDriver`)를 Action 단위로 쪼갤지, 지금처럼
   Task 단위(`run_dispense_command`)로 유지하고 내부에서만 Action을 기록할지**
   — 김연서·안윤수 선배 로봇 제어 코드가 Action 단위로 나뉘어 있는지 확인 필요
4. **concentration 단위 표준화** — mg/mL, M(몰농도), wt% 등 실험마다 다를 수 있어
   단위 변환 처리가 필요할 수 있음

---

## 6. 다음 단계 (코드 구현 체크리스트)

- [ ] `ActionType` enum + `Action` Pydantic 모델 (`src/database/models.py`에 추가)
- [ ] `MaterialRole` enum + `MaterialUsage` Pydantic 모델
- [ ] `Task.actions: list[Action]`, `Task.material_usage: Optional[MaterialUsage]` 필드 추가
- [ ] `run_dispense_command()`를 13단계 Action 시퀀스를 생성하도록 확장
- [ ] RETRACT→DOOR_CLOSE 안전 순서 검증 로직 (실패 시 flow 중단)
- [ ] mongomock 테스트: Action 시퀀스 생성, 안전 순서 위반 시 에러, MaterialUsage 기록 확인
- [ ] `docs/db_schema.md`에 Action/MaterialUsage 반영
