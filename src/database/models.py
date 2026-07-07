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


class Task(BaseModel):
    """
    프로토콜의 개별 Step 1개 (예: "D-1")에 대응.
    ActionGraph의 Association Edge(operation ↔ 대상) + Reference Edge(input/output 참조)를
    input_refs / output_refs 필드로 표현한다.
    """
    task_id: str
    experiment_id: str
    phase: Literal["A", "B", "C", "D", "E", "F", "G"]
    step_code: str                  # 원본 프로토콜 추적용: "D-1", "F-2" 등
    operation: OperationType
    parameters: dict[str, Any]      # OPERATION_PARAM_MODEL로 검증된 값 (dict로 저장)
    device_id: Optional[str] = None  # Manual인 경우 None
    input_refs: list[str] = []      # 참조하는 이전 Sample.sample_id들
    output_refs: list[str] = []     # 이 Task가 생성하는 Sample.sample_id들
    repeat_of: Optional[RepeatParams] = None
    order_critical: bool = False    # TRANSFER의 order_critical과 별개로 Task 레벨에서도 노출
    status: Literal[
        "pending", "running", "success", "failed", "held"
    ] = "pending"
    actual_values: dict[str, Any] = {}   # VERIFY_MASS 실측값 등 (예: {"mass_metal_mg": 95.2})
    prefect_task_run_id: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    def required_device_type(self) -> str:
        return OPERATION_REQUIRED_DEVICE_TYPE[self.operation]


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
