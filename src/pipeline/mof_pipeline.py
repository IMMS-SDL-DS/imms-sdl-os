"""
MOF SDL OS — Prefect 기반 기본 파이프라인
====================================
실험 데이터 수집 → 전처리 → DB 저장 → 다음 실험 제안
의 흐름을 Prefect flow로 구현한 스타터 코드
"""

from prefect import flow, task
from datetime import datetime
import json


# ── Task 1: 실험 조건 로드 ────────────────────────────────────────────
@task(name="load_experiment_conditions", retries=2)
def load_conditions(experiment_id: str) -> dict:
    """
    실험 조건을 DB 또는 파일에서 불러옵니다.
    TODO: MongoDB 연결로 교체
    """
    # 임시 더미 데이터 (실제 구현 시 DB 쿼리로 교체)
    conditions = {
        "experiment_id": experiment_id,
        "temperature_c": 120,
        "reaction_time_h": 24,
        "solvent": "DMF",
        "metal_source": "Zn(NO3)2",
        "linker": "BDC",
        "concentration_mm": 50,
    }
    print(f"[{experiment_id}] 실험 조건 로드 완료")
    return conditions


# ── Task 2: 장치에서 결과 수집 ──────────────────────────────────────
@task(name="collect_device_output", retries=3, retry_delay_seconds=10)
def collect_xrd_result(experiment_id: str, device_id: str = "XRD-001") -> dict:
    """
    XRD 장치에서 측정 결과를 수집합니다.
    TODO: 실제 장치 API 연결로 교체
    """
    # 임시 더미 결과
    result = {
        "experiment_id": experiment_id,
        "device_id": device_id,
        "measured_at": datetime.now().isoformat(),
        "xrd_peaks": [7.2, 10.1, 14.3, 17.8],   # 2θ 피크 위치
        "yield_percent": 83.5,
        "raw_file_path": f"data/xrd/{experiment_id}.xy"
    }
    print(f"[{device_id}] XRD 측정 완료: {experiment_id}")
    return result


# ── Task 3: 데이터 전처리 ────────────────────────────────────────────
@task(name="preprocess_result")
def preprocess(conditions: dict, result: dict) -> dict:
    """
    실험 조건 + 결과를 AI 학습용 정형 데이터로 변환합니다.
    """
    processed = {
        # 실험 조건 (입력)
        "temperature_c": conditions["temperature_c"],
        "reaction_time_h": conditions["reaction_time_h"],
        "solvent": conditions["solvent"],
        "concentration_mm": conditions["concentration_mm"],
        # 실험 결과 (출력)
        "yield_percent": result["yield_percent"],
        "n_xrd_peaks": len(result["xrd_peaks"]),
        "primary_peak": result["xrd_peaks"][0] if result["xrd_peaks"] else None,
        # 메타데이터
        "experiment_id": conditions["experiment_id"],
        "processed_at": datetime.now().isoformat(),
    }
    print(f"전처리 완료: {processed['experiment_id']}")
    return processed


# ── Task 4: DB 저장 ─────────────────────────────────────────────────
@task(name="save_to_database")
def save_to_db(processed_data: dict) -> bool:
    """
    전처리된 데이터를 DB에 저장합니다.
    TODO: MongoDB pymongo 연결로 교체
    """
    # 임시: JSON 파일로 저장
    path = f"logs/{processed_data['experiment_id']}_result.json"
    print(f"DB 저장 완료: {path}")
    print(json.dumps(processed_data, indent=2, ensure_ascii=False))
    return True


# ── Task 5: 다음 실험 제안 (추후 BO 연결) ──────────────────────────
@task(name="suggest_next_experiment")
def suggest_next(processed_data: dict) -> dict:
    """
    현재 결과를 바탕으로 다음 실험 조건을 제안합니다.
    TODO: Bayesian Optimization 모듈 연결
    """
    # 임시: 간단한 규칙 기반 제안
    next_conditions = {
        "temperature_c": processed_data["temperature_c"] + 10,
        "reaction_time_h": processed_data["reaction_time_h"],
        "solvent": processed_data["solvent"],
        "concentration_mm": processed_data["concentration_mm"],
        "reason": f"수율 {processed_data['yield_percent']}% → 온도 상향 실험"
    }
    print(f"다음 실험 제안: {next_conditions}")
    return next_conditions


# ── Main Flow ────────────────────────────────────────────────────────
@flow(name="MOF-SDL-Pipeline", log_prints=True)
def mof_sdl_pipeline(experiment_id: str = "MOF-2025-001"):
    """
    MOF 자율실험실 데이터 파이프라인
    
    Design → Make → Test → Analyze 루프의 소프트웨어 레이어
    """
    print(f"\n{'='*50}")
    print(f"  MOF SDL 파이프라인 시작: {experiment_id}")
    print(f"{'='*50}\n")

    # Step 1: 실험 조건 로드
    conditions = load_conditions(experiment_id)

    # Step 2: 장치 결과 수집
    result = collect_xrd_result(experiment_id)

    # Step 3: 전처리
    processed = preprocess(conditions, result)

    # Step 4: DB 저장
    save_to_db(processed)

    # Step 5: 다음 실험 제안
    next_exp = suggest_next(processed)

    print(f"\n✅ 파이프라인 완료: {experiment_id}")
    return next_exp


# ── 실행 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mof_sdl_pipeline(experiment_id="MOF-2025-001")
