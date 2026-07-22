# 🔗 Scheduler Interface — Job Schema Contract

> Learning-Aware Scheduler(Dr.Mehdi)와 MOF SDL OS(공유 DB) 사이의 인터페이스 정의.
> 슬라이드(2026.7.15) 4번 "Architecture"에 명시된 계약:
> "reads {value, duration, device, precedence, deadline} · returns ordering"

---

## 1. Job Schema — 스케줄러가 읽는 형태

DB의 `task` 컬렉션에서 `status="pending"`인 Task들이 스케줄링 대상이며,
`get_scheduler_job_queue()`가 아래 형태로 변환해서 반환한다.

```python
{
    "job_id": str,           # Task.task_id
    "value": float | None,   # 이 결과가 학습에 얼마나 가치있는지 (Yuhyun의 BO 플랫폼이 채움)
    "duration": float | None,  # 예상 실행 시간 (초)
    "device": str | None,    # 필요한 장비 ID (device_id)
    "precedence": list[str], # 이 Job보다 먼저 끝나야 하는 다른 job_id 목록
    "deadline": datetime | None,  # 캠페인 마감 시한
}
```

**호출 예시**:
```python
from src.database.mongo_client import get_database, get_scheduler_job_queue

db = get_database()
queue = get_scheduler_job_queue(db)                       # 전체 pending job
queue = get_scheduler_job_queue(db, experiment_id="e1")   # 특정 캠페인만
```

## 2. Ordering — 스케줄러가 쓰는 형태

스케줄러가 계산을 마치면, 실행 순서를 `job_id` 리스트(먼저 실행할 순서대로)로
돌려주고, `apply_scheduler_ordering()`으로 DB에 반영한다.

```python
from src.database.mongo_client import apply_scheduler_ordering

ordering = ["j3", "j1", "j2"]  # j3를 가장 먼저 실행
apply_scheduler_ordering(db, ordering)
```

내부적으로 각 Task 문서의 `scheduler_priority` 필드에 순서(0부터 시작, 낮을수록
먼저 실행)를 기록한다. SDL OS(Prefect)는 이 필드를 참고해서 실행 순서를 결정한다
(Prefect 쪽 실제 소비 로직은 아직 미구현 — 3번 참고).

## 3. Task 모델의 스케줄러 관련 필드 (`src/database/models.py`)

| 필드 | 타입 | 채우는 주체 | 설명 |
|---|---|---|---|
| `scheduler_value` | `float \| None` | Yuhyun 플랫폼 | BO 캠페인에서 이 실험의 예상 정보 가치 |
| `scheduler_duration_estimate_sec` | `float \| None` | (합의 필요) | 예상 실행 시간. 지금은 `parameters` 안에 오퍼레이션별로 흩어져 있는 duration(`HeatParams.duration_h` 등)과 별개로, 스케줄러가 비교하기 쉬운 통일된 초 단위 필드 |
| `scheduler_precedence` | `list[str]` | SDL OS (자동 계산 가능) | 순서 제약. `input_refs`(물질 참조)와는 다른 개념 — 물질이 안 겹쳐도 순서가 강제될 수 있음(예: `order_critical` Task) |
| `scheduler_deadline` | `datetime \| None` | (합의 필요) | 캠페인 마감. 캠페인 단위(Experiment)로 관리할지, Task 단위로 상속시킬지 논의 필요 |
| `scheduler_priority` | `int \| None` | Scheduler (write) | 스케줄러가 계산한 실행 순서. `None`이면 아직 미배정 |

## 4. 아직 결정 안 된 것 (formulation 세션에서 논의할 것)

- **`value`를 누가/언제 채우는가**: Task 생성 시점에 미리 알 수 있는 값인지,
  아니면 이전 결과를 보고 동적으로 갱신되는 값인지 (후자라면 업데이트 API 별도 필요)
- **`duration` 추정 방식**: 프로토콜에 명시된 값(예: HEAT 24h) 그대로 쓸지,
  실제 실행 로그 기반으로 통계적으로 추정할지 (교수님 슬라이드의 "MOF dosing cell
  timings (4 min/vial, RSD 0.32%)"처럼 실측 통계를 쓰는 방향인 듯)
- **`deadline`이 Task 단위인지 Experiment(캠페인) 단위인지**: 지금 모델은 Task에
  필드를 뒀지만, 실제로는 캠페인 전체가 하나의 deadline을 공유할 가능성이 높음
- **Prefect 쪽에서 `scheduler_priority`를 실제로 어떻게 소비할지**: 지금은 DB에
  기록만 되고, `zr_btc_synthesis_flow.py`가 이 값을 읽어서 실행 순서를 바꾸는
  로직은 아직 없음 (다음 작업)

## 5. 테스트

`tests/test_scheduler_interface.py` — job schema 변환, pending 필터링,
experiment 필터링, ordering 저장까지 5개 테스트로 검증 완료.
