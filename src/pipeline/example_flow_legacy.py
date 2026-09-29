"""
[LEGACY / 템플릿] SDL 데이터 수집 파이프라인 예시 (Prefect 기반)

실제 구현 전 구조를 잡기 위해 초기에 작성한 템플릿 코드입니다.
현재 실제로 동작하는 flow는 zr_btc_synthesis_flow.py / live_16step_flow.py이며,
이 파일은 실행되지 않습니다. 구조 참고용으로만 남겨둡니다.
"""

from prefect import flow, task
from datetime import datetime


@task(name="장치 데이터 수집")
def collect_device_data(device_id: str) -> dict:
    """
    실험 장치(XRD 등)에서 데이터를 수집한다.
    TODO: 실제 장치 API로 교체
    """
    return {
        "device_id": device_id,
        "timestamp": datetime.now().isoformat(),
        "data": {}  # 실제 장치 데이터로 교체
    }


@task(name="데이터 정제")
def preprocess_data(raw_data: dict) -> dict:
    """
    수집된 원시 데이터를 DB 저장 가능한 형태로 변환한다.
    """
    # TODO: 실험 조건 / 결과 파싱 로직 구현
    processed = {
        "device_id": raw_data["device_id"],
        "timestamp": raw_data["timestamp"],
        "conditions": {},   # 실험 조건 (온도, 농도 등)
        "results": {},      # 측정 결과 (스펙트럼, 수율 등)
    }
    return processed


@task(name="DB 저장")
def save_to_database(data: dict) -> bool:
    """
    정제된 데이터를 MongoDB에 저장한다.
    """
    # TODO: MongoDB 연결 구현
    print(f"[DB 저장] {data['device_id']} @ {data['timestamp']}")
    return True


@flow(name="MOF SDL 데이터 파이프라인")
def sdl_data_pipeline(device_id: str = "xrd_001"):
    """
    SDL 메인 파이프라인:
    장치 데이터 수집 → 정제 → DB 저장
    """
    raw = collect_device_data(device_id)
    processed = preprocess_data(raw)
    save_to_database(processed)
    print("✅ 파이프라인 완료")


if __name__ == "__main__":
    sdl_data_pipeline()
