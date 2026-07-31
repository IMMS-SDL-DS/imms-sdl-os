"""
MOF SDL OS — 데이터 모델 (Pydantic)
====================================
2026.01.28~29 Zr-BTC MOF 합성 프로토콜(실험팀 제공)을 기반으로 설계.

설계 근거:
- OCTOPUS (Yoo et al., 2024): Platform > Module > Task > Action 계층 구조,
  Task별 masking table(필요 장비 목록)로 충돌 방지
- ActionGraph (arXiv 2512.02947): 합성 레시피를 DAG로 표현.
  Node = 물질/조건/장치, Edge = Association(조작-대상) + Reference(이전 output → 다음 input)
- 실험팀 프로토콜의 "Unit Operation Schema" (OP-01~OP-19)를 그대로 Enum + 타입 검증으로 이식

이 파일은 4개 핵심 컬렉션(Experiment / Task / Device / Sample)의 스키마를
MongoDB에 넣기 전에 파이썬 레벨에서 검증하기 위한 Pydantic 모델을 정의한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# 0. Unit Operation 정의 (실험팀 프로토콜 §4, §5 기반)
# ─────────────────────────────────────────────────────────────

class OperationType(str, Enum):
    """OP-01 ~ OP-19. 프로토콜의 Unit Operation Schema 표와 1:1 대응."""

    DISPENSE_SOLID = "DISPENSE_SOLID"       # OP-01
    VERIFY_MASS = "VERIFY_MASS"             # OP-02
    DISPENSE = "DISPENSE"                   # OP-03
    TRANSFER = "TRANSFER"                   # OP-04
    DECANT = "DECANT"                       # OP-05
    MIX = "MIX"                             # OP-06
    SONICATE = "SONICATE"                   # OP-07
    CENTRIFUGE = "CENTRIFUGE"               # OP-08
    VORTEX = "VORTEX"                       # OP-09
    BALANCE_CHECK = "BALANCE_CHECK"         # OP-10
    SEAL = "SEAL"                           # OP-11
    HEAT = "HEAT"                           # OP-12
    DRY = "DRY"                             # OP-13
    SAMPLE = "SAMPLE"                       # OP-14
    ANALYZE_XRD = "ANALYZE_XRD"             # OP-15
    REPEAT = "REPEAT"                       # OP-16
    SOLVENT_CHANGE = "SOLVENT_CHANGE"       # OP-17
    GRIND = "GRIND"                         # OP-18
    ANALYZE_OM = "ANALYZE_OM"               # OP-19


# 각 Operation이 실제로 어떤 장비를 필요로 하는지 (OCTOPUS의 masking table 개념).
# Task 실행 전 Resource Manager가 이 목록으로 Device 충돌 여부를 체크한다.
OPERATION_REQUIRED_DEVICE_TYPE: dict[OperationType, str] = {
    OperationType.DISPENSE_SOLID: "solid_dispenser",
    OperationType.VERIFY_MASS: "balance",
    OperationType.DISPENSE: "liquid_handler",
    OperationType.TRANSFER: "liquid_handler",
    OperationType.DECANT: "liquid_handler",  # or manual
    OperationType.MIX: "liquid_handler",
    OperationType.SONICATE: "sonicator",
    OperationType.CENTRIFUGE: "centrifuge",
    OperationType.VORTEX: "vortex_mixer",
    OperationType.BALANCE_CHECK: "balance",
    OperationType.SEAL: "manual",
    OperationType.HEAT: "heater",
    OperationType.DRY: "manual",
    OperationType.SAMPLE: "manual",
    OperationType.ANALYZE_XRD: "xrd",
    OperationType.REPEAT: "none",
    OperationType.SOLVENT_CHANGE: "liquid_handler",
    OperationType.GRIND: "manual",
    OperationType.ANALYZE_OM: "optical_microscope",
}


# 자동 재시도(retry)가 안전한 Operation만 표시.
# ── 안전(재시도해도 부작용 없음): 측정/판독만 하고 물질 상태를 바꾸지 않는 것들.
#    예: VERIFY_MASS는 저울 값을 다시 읽기만 함, ANALYZE_XRD/ANALYZE_OM도 측정만 함.
# ── 위험(재시도하면 안 됨): 물리적으로 물질을 옮기거나 바꾸는 것들.
#    예: DISPENSE_SOLID를 재시도하면, 실패 원인이 "통신 에러"가 아니라
#    "이미 절반쯤 분주된 상태"였을 경우 목표량의 2배가 들어갈 수 있음.
#    TRANSFER, HEAT, CENTRIFUGE 등도 마찬가지로 "이미 일부 실행됐을 가능성"이 있어 위험.
SAFE_TO_RETRY_OPERATIONS: frozenset[OperationType] = frozenset({
    OperationType.VERIFY_MASS,
    OperationType.ANALYZE_XRD,
    OperationType.ANALYZE_OM,
    OperationType.BALANCE_CHECK,
})


def is_safely_retryable(operation: OperationType) -> bool:
    """이 Operation이 통신 에러 등으로 실패했을 때 자동 재시도해도 안전한지."""
    return operation in SAFE_TO_RETRY_OPERATIONS


# ─────────────────────────────────────────────────────────────
# 1. Operation별 Parameter 모델 (프로토콜 §5 Variable Schema 그대로 이식)
# ─────────────────────────────────────────────────────────────

class DispenseSolidParams(BaseModel):
    reagent: str
    mass_mg: float
    tolerance_mg: float = 5.0
    vessel: str


class VerifyMassParams(BaseModel):
    vessel: str
    expected_mass_mg: float


class DispenseParams(BaseModel):
    reagent: str
    volume_ml: float
    vessel: str


class TransferParams(BaseModel):
    source: str
    dest: str
    volume_ml: Optional[float] = None  # null 허용 (전량 이동 등)
    order_critical: bool = False
    # 프로토콜 Notes: "혼합 순서(L→M) 반드시 준수 — 역순 시 부산물 생성"
    # order_critical=True인 Task는 Prefect flow에서 순서 위반 시 강제 실패 처리


class DecantParams(BaseModel):
    vessel: str
    waste_container: str


class MixParams(BaseModel):
    vessel: str
    method: Literal["pipette", "vortex", "stir"]
    cycles: int = 5


class SonicateParams(BaseModel):
    vessel: str
    duration_min: int
    temp_c: Optional[float] = None


class CentrifugeParams(BaseModel):
    vessel: str
    rpm: int
    duration_min: float


class VortexParams(BaseModel):
    vessel: str
    duration_sec: int


class BalanceCheckParams(BaseModel):
    vessel_pair: list[str] = Field(min_length=2, max_length=2)
    tolerance_g: float = 0.05


class SealParams(BaseModel):
    vessel: str
    seal_type: Literal["screw_cap", "crimp"]


class HeatParams(BaseModel):
    vessel: str
    temp_c: float
    duration_h: float
    mode: Literal["static", "stir"] = "static"


class DryParams(BaseModel):
    sample: str
    method: Literal["filter", "airgun", "vacuum"]


class SampleOpParams(BaseModel):
    """OP-14 SAMPLE (Python 'sample' 키워드와 구분하기 위해 클래스명은 SampleOpParams)"""
    source: str
    amount: str
    dest_holder: str


class AnalyzeXrdParams(BaseModel):
    sample_holder: str


class RepeatParams(BaseModel):
    start_step: str
    end_step: str
    count: int
    solvent: Optional[str] = None


class SolventChangeParams(BaseModel):
    from_solvent: str
    to_solvent: str


class GrindParams(BaseModel):
    sample: str
    duration_min: Optional[int] = None


class AnalyzeOmParams(BaseModel):
    sample_holder: str


# Operation → Parameter 모델 매핑 (Task 생성 시 이걸로 validate)
OPERATION_PARAM_MODEL: dict[OperationType, type[BaseModel]] = {
    OperationType.DISPENSE_SOLID: DispenseSolidParams,
    OperationType.VERIFY_MASS: VerifyMassParams,
    OperationType.DISPENSE: DispenseParams,
    OperationType.TRANSFER: TransferParams,
    OperationType.DECANT: DecantParams,
    OperationType.MIX: MixParams,
    OperationType.SONICATE: SonicateParams,
    OperationType.CENTRIFUGE: CentrifugeParams,
    OperationType.VORTEX: VortexParams,
    OperationType.BALANCE_CHECK: BalanceCheckParams,
    OperationType.SEAL: SealParams,
    OperationType.HEAT: HeatParams,
    OperationType.DRY: DryParams,
    OperationType.SAMPLE: SampleOpParams,
    OperationType.ANALYZE_XRD: AnalyzeXrdParams,
    OperationType.REPEAT: RepeatParams,
    OperationType.SOLVENT_CHANGE: SolventChangeParams,
    OperationType.GRIND: GrindParams,
    OperationType.ANALYZE_OM: AnalyzeOmParams,
}


def validate_operation_params(operation: OperationType, params: dict) -> BaseModel:
    """Task.parameters를 operation 종류에 맞는 Pydantic 모델로 검증한다."""
    model = OPERATION_PARAM_MODEL[operation]
    return model(**params)


# ─────────────────────────────────────────────────────────────
# 2. 핵심 컬렉션: Experiment / Task / Device / Sample
# ─────────────────────────────────────────────────────────────

class ReagentSpec(BaseModel):
    """Experiment.reagents 리스트의 원소. 프로토콜 §2 시약 표에 대응."""
    name: str
    role: str            # "Metal Source" | "Organic Linker" | "Solvent" | ...
    amount: str          # "97 mg", "3 mL" 등 원본 표기 유지
    dispense_device: str
    notes: Optional[str] = None


class Experiment(BaseModel):
    """하나의 합성 실험 캠페인. 예: Zr-BTC MOF Synthesis Protocol 1회 실행."""
    experiment_id: str
    name: str                       # "Zr-BTC MOF Synthesis"
    protocol_version: str           # "26.01.28~26.01.29"
    target_material: str            # "Zr-BTC MOF"
    researcher: str = "손시영"
    status: Literal["planned", "running", "completed", "failed", "held"] = "planned"
    reagents: list[ReagentSpec] = []
    phase_sequence: list[str] = ["A", "B", "C", "D", "E", "F", "G"]
    created_at: datetime = Field(default_factory=datetime.now)
    notes: list[str] = []


# ─────────────────────────────────────────────────────────────
# Action 레벨 모델 — Task(예: DISPENSE_SOLID) 내부의 세부 로봇/저울 동작.
# 설계 근거: docs/solid_dosing_workflow.md (선배가 준 고체 분주 12단계 workflow)
# ─────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    """
    12단계 고체 분주 workflow를 7개의 재사용 가능한 타입으로 일반화한 것.
    같은 타입이 여러 단계에서 반복 사용됨 (예: PICK은 헤드 집기·바이알 집기 둘 다).
    """
    PICK = "PICK"              # 로봇팔이 물체(헤드/바이알)를 집음
    PLACE = "PLACE"            # 로봇팔이 물체를 내려놓음
    MOUNT = "MOUNT"            # 헤드를 저울에 장착
    RETRACT = "RETRACT"        # 로봇팔이 작업 공간 밖으로 빠져나옴
    DOOR_OPEN = "DOOR_OPEN"    # 저울 문 열기
    DOOR_CLOSE = "DOOR_CLOSE"  # 저울 문 닫기
    DOSE = "DOSE"              # 설정량만큼 실제 계량 분주


class Action(BaseModel):
    """
    DISPENSE_SOLID 같은 Task 하나 안에서 일어나는 세부 동작 1개.
    선배가 준 12단계 workflow의 각 단계가 Action 레코드 하나에 대응한다
    (6번 "로봇팔 빠짐→문 닫힘"은 RETRACT+DOOR_CLOSE 두 Action으로 쪼개져서 총 13개).
    """
    action_id: str
    parent_task_id: str             # 이 Action이 속한 Task(예: DISPENSE_SOLID)의 task_id
    sequence_index: int             # 1부터 시작하는 실행 순서
    action_type: ActionType
    object_ref: Optional[str] = None      # "head_ZrOCl2", "vial_003" 등 대상 물체
    source_location: Optional[str] = None  # 어디서 (예: "head_rack")
    dest_location: Optional[str] = None    # 어디로 (예: "balance_center")
    status: Literal["pending", "running", "success", "failed"] = "pending"
    safety_critical: bool = False
    # True면 바로 이전 Action이 반드시 success여야 이 Action을 시작할 수 있음.
    # 예: RETRACT가 성공해야 DOOR_CLOSE를 실행 — 안 그러면 로봇팔과 문이 충돌할 수 있음.
    # 기존 Task.order_critical(물질 흐름 순서)과는 다른 카테고리: 이건 "물리적 충돌 방지"용.
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


# 12단계 workflow → 13개 Action 시퀀스로 확장하는 템플릿.
# (parent_task_id, action_id는 실행 시점에 채워짐 — 여기선 타입/순서만 정의)
SOLID_DOSING_ACTION_SEQUENCE: list[dict] = [
    {"sequence_index": 1,  "action_type": ActionType.PICK,       "object_ref": "head", "source_location": "head_rack"},
    {"sequence_index": 2,  "action_type": ActionType.MOUNT,      "object_ref": "head", "dest_location": "balance"},
    {"sequence_index": 3,  "action_type": ActionType.PICK,       "object_ref": "vial", "source_location": "vial_rack"},
    {"sequence_index": 4,  "action_type": ActionType.DOOR_OPEN},
    {"sequence_index": 5,  "action_type": ActionType.PLACE,      "object_ref": "vial", "dest_location": "balance_center"},
    {"sequence_index": 6,  "action_type": ActionType.RETRACT},
    {"sequence_index": 7,  "action_type": ActionType.DOOR_CLOSE, "safety_critical": True},  # RETRACT(6) 성공 필수
    {"sequence_index": 8,  "action_type": ActionType.DOSE,       "object_ref": "material"},
    {"sequence_index": 9,  "action_type": ActionType.DOOR_OPEN},
    {"sequence_index": 10, "action_type": ActionType.PICK,       "object_ref": "vial", "source_location": "balance_center"},
    {"sequence_index": 11, "action_type": ActionType.DOOR_CLOSE},
    {"sequence_index": 12, "action_type": ActionType.PLACE,      "object_ref": "vial", "dest_location": "vial_rack"},
    {"sequence_index": 13, "action_type": ActionType.PLACE,      "object_ref": "head", "dest_location": "head_rack"},
]


# ─────────────────────────────────────────────────────────────
# Material 추적 모델 — metal/ligand/solvent 등 실제 사용 물질 기록
# ─────────────────────────────────────────────────────────────

class MaterialRole(str, Enum):
    METAL = "metal"
    LIGAND = "ligand"
    SOLVENT = "solvent"
    MODULATOR = "modulator"


class MaterialUsage(BaseModel):
    """
    DISPENSE_SOLID Task 하나에 자연스럽게 1:1로 붙는 실제 사용 물질 기록.
    Experiment.reagents(ReagentSpec)가 "계획값"이라면, 이건 "이번 배치에 실제로
    어떤 물질을 얼마나 썼는지"를 실행 시점에 기록하는 값.
    """
    material_name: str              # "ZrOCl2"
    role: MaterialRole
    concentration: Optional[float] = None
    concentration_unit: Optional[str] = None   # "M", "mg/mL" 등
    target_mass_mg: float
    actual_mass_mg: Optional[float] = None     # VERIFY_MASS 결과로 채워짐
    head_id: Optional[str] = None              # 어느 도징헤드 카트리지를 썼는지
    vial_id: Optional[str] = None


class Task(BaseModel):
    """
    프로토콜의 개별 Step 1개 (예: "D-1")에 대응.
    ActionGraph의 Association Edge(operation ↔ 대상) + Reference Edge(input/output 참조)를
    input_refs / output_refs 필드로 표현한다.

    scheduler_* 필드들은 Mehdi의 Learning-Aware Scheduler와의 인터페이스다.
    Task 실행 자체와는 무관하고, "이 Task를 언제/어떤 순서로 실행할지" 결정하는 데만 쓰인다.
    job schema 계약: {value, duration, device, precedence, deadline}
    (device는 이미 있는 device_id 필드를 그대로 재사용)
    자세한 내용은 docs/scheduler_interface.md 참고.

    actions / material_usage는 고체 분주처럼 세부 로봇 동작·물질 추적이 필요한 Task에서만
    채워진다 (예: DISPENSE_SOLID). 다른 오퍼레이션은 비워둬도 됨.
    자세한 내용은 docs/solid_dosing_workflow.md 참고.
    """
    task_id: str
    experiment_id: str
    phase: Literal["A", "B", "C", "D", "E", "F", "G"]
    step_code: str                  # 원본 프로토콜 추적용: "D-1", "F-2" 등
    operation: OperationType
    parameters: dict[str, Any]      # OPERATION_PARAM_MODEL로 검증된 값 (dict로 저장)
    device_id: Optional[str] = None  # Manual인 경우 None — job schema의 "device"
    input_refs: list[str] = []      # 참조하는 이전 Sample.sample_id들 (물질 흐름)
    output_refs: list[str] = []     # 이 Task가 생성하는 Sample.sample_id들 (물질 흐름)
    repeat_of: Optional[RepeatParams] = None
    order_critical: bool = False    # TRANSFER의 order_critical과 별개로 Task 레벨에서도 노출
    status: Literal[
        "pending", "running", "success", "failed", "held"
    ] = "pending"
    actual_values: dict[str, Any] = {}   # VERIFY_MASS 실측값 등 (예: {"mass_metal_mg": 95.2})
    prefect_task_run_id: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    # ── Action 레벨 세부 실행 로그 (고체 분주 등에서 사용) ──────────────
    actions: list[Action] = []
    material_usage: Optional[MaterialUsage] = None

    # ── Scheduler 인터페이스 필드 (job schema: value/duration/device/precedence/deadline) ──
    scheduler_value: Optional[float] = None
    # 이 Task 결과가 학습(BO 캠페인)에 얼마나 가치있는지 — Yuhyun의 최적화 플랫폼이 채움.
    # 값이 클수록 "이 결과를 빨리 알수록 다음 실험 설계가 좋아진다"는 뜻.

    scheduler_duration_estimate_sec: Optional[float] = None
    # 예상 실행 시간(초). parameters 안의 duration_h 등과는 별개로,
    # 스케줄러가 여러 오퍼레이션을 비교할 때 쓸 수 있는 통일된 단위.

    scheduler_precedence: list[str] = []
    # 이 Task가 실행되기 전에 반드시 끝나야 하는 다른 Task의 task_id 목록.
    # input_refs(물질 참조)와는 목적이 다름 — precedence는 순서 제약 그 자체를 표현.

    scheduler_deadline: Optional[datetime] = None
    # 이 Task가 속한 캠페인의 마감 시한 (finite campaign horizon).

    scheduler_priority: Optional[int] = None
    # 스케줄러가 계산 후 돌려주는 실행 순서 (낮을수록 먼저 실행). None이면 아직 미배정.

    def required_device_type(self) -> str:
        return OPERATION_REQUIRED_DEVICE_TYPE[self.operation]

    def to_scheduler_job(self) -> dict:
        """스케줄러가 읽을 job schema 형태로 변환: {value, duration, device, precedence, deadline}."""
        return {
            "job_id": self.task_id,
            "value": self.scheduler_value,
            "duration": self.scheduler_duration_estimate_sec,
            "device": self.device_id,
            "precedence": self.scheduler_precedence,
            "deadline": self.scheduler_deadline,
            "status": self.status,
        }

    def build_solid_dosing_actions(self) -> list[Action]:
        """
        SOLID_DOSING_ACTION_SEQUENCE 템플릿으로 이 Task의 13개 Action을 생성해서
        self.actions에 채운다. DISPENSE_SOLID Task에서 호출하는 용도.
        """
        built: list[Action] = []
        for i, tmpl in enumerate(SOLID_DOSING_ACTION_SEQUENCE):
            built.append(Action(
                action_id=f"{self.task_id}_action{i+1}",
                parent_task_id=self.task_id,
                **tmpl,
            ))
        self.actions = built
        return built

    def validate_action_safety_order(self) -> None:
        """
        safety_critical Action은 바로 이전 Action이 success여야 한다.
        위반 시 ValueError를 던진다 (예: RETRACT 실패했는데 DOOR_CLOSE가 진행된 경우).
        """
        for i, action in enumerate(self.actions):
            if action.safety_critical and i > 0:
                prev = self.actions[i - 1]
                if prev.status != "success":
                    raise ValueError(
                        f"안전 순서 위반: {action.action_type}(#{action.sequence_index})은 "
                        f"이전 Action({prev.action_type}, status={prev.status})이 success여야 "
                        f"실행 가능합니다."
                    )


class Device(BaseModel):
    """실험 장비. Opentron Flex처럼 여러 Phase에서 공유되는 장비는 shared_phases로 표시."""
    device_id: str
    name: str                       # "Opentron Flex", "Mettler Toledo", "Centrifuge" ...
    device_type: str                # "liquid_handler" | "balance" | "solid_dispenser" | ...
    connection: Literal["python_api", "onoff_param", "manual"]
    shared_phases: list[str] = []   # 이 장비가 쓰이는 Phase들 (예: Opentron -> ["A","B","C","D","F"])
    status: Literal["idle", "busy", "offline", "maintenance"] = "idle"
    last_used_at: Optional[datetime] = None


class Sample(BaseModel):
    """
    프로토콜 상의 중간/최종 산출물.
    예: homo_solution, metal_sol, ligand_sol, rxn_mixture, MOF_slurry,
        xrd_result_1, washed_MOF, xrd_result_final
    """
    sample_id: str
    experiment_id: str
    sample_code: str                # "MOF_slurry", "xrd_result_final" 등 원본 명칭
    sample_type: Literal["solution", "slurry", "solid", "xrd_data", "om_data"]
    produced_by_task_id: Optional[str] = None
    consumed_by_task_ids: list[str] = []
    properties: dict[str, Any] = {}  # XRD peak 리스트, 실측 mass 등
    created_at: datetime = Field(default_factory=datetime.now)


# ─────────────────────────────────────────────────────────────
# 3. 간단 셀프 테스트 (python -m src.database.models 로 실행)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 프로토콜 Phase D-1 (TRANSFER, order_critical) 검증 예시
    params = validate_operation_params(
        OperationType.TRANSFER,
        {"source": "ligand_sol", "dest": "metal_sol", "volume_ml": None, "order_critical": True},
    )
    print("✅ TRANSFER 파라미터 검증 통과:", params)

    task = Task(
        task_id="task_D1",
        experiment_id="exp_zrbtc_001",
        phase="D",
        step_code="D-1",
        operation=OperationType.TRANSFER,
        parameters=params.model_dump(),
        device_id="dev_opentron_flex",
        input_refs=["sample_ligand_sol", "sample_metal_sol"],
        output_refs=["sample_rxn_mixture"],
        order_critical=True,
    )
    print("✅ Task 모델 생성 완료:", task.required_device_type())
