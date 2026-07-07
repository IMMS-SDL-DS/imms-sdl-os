# 🗄️ MOF 실험 DB 스키마 설계

> ChemOS 2.0의 device/job/devicelog 구조를 기반으로  
> MOF 실험 데이터에 맞게 확장한 스키마 초안

---

## 설계 원칙

1. **범용성** — 어떤 MOF 실험에도 적용 가능
2. **추적 가능성** — 실험 조건·결과·장비 상태 전부 기록
3. **AI 친화적** — 바로 학습에 쓸 수 있는 정형 데이터
4. **FAIR 원칙** — Findable, Accessible, Interoperable, Reusable

---

## 핵심 테이블 구조

### 1. `experiment` — 실험 단위
```python
{
    "experiment_id": "MOF-2025-001",
    "created_at": "2025-07-01T09:00:00",
    "status": "pending | running | completed | failed",
    "researcher": "손시영",
    "target_material": "IRMOF-1",
    "notes": ""
}
```

### 2. `condition` — 실험 조건
```python
{
    "experiment_id": "MOF-2025-001",
    "temperature_c": 120,
    "reaction_time_h": 24,
    "solvent": "DMF",
    "metal_source": "Zn(NO3)2",
    "linker": "BDC",
    "concentration_mm": 50,
    "volume_ml": 10
}
```

### 3. `result` — 실험 결과
```python
{
    "experiment_id": "MOF-2025-001",
    "yield_percent": 85.3,
    "purity": "high | medium | low",
    "xrd_file_path": "data/xrd/MOF-2025-001.xy",
    "surface_area_m2g": 1200,
    "characterization_notes": ""
}
```

### 4. `device` — 연결된 장비
```python
{
    "device_id": "XRD-001",
    "device_type": "XRD",
    "model": "Rigaku MiniFlex",
    "status": "idle | busy | error",
    "last_calibrated": "2025-07-01"
}
```

### 5. `job` — 장비 작업 큐
```python
{
    "job_id": "JOB-001",
    "experiment_id": "MOF-2025-001",
    "device_id": "XRD-001",
    "status": "queued | running | done | failed",
    "started_at": None,
    "completed_at": None
}
```

### 6. `devicelog` — 장비 실행 기록
```python
{
    "log_id": "LOG-001",
    "job_id": "JOB-001",
    "timestamp": "2025-07-01T10:30:00",
    "message": "XRD scan started",
    "level": "INFO | WARNING | ERROR"
}
```

---

## 관계도

```
experiment
    ├── condition (1:1)
    ├── result    (1:1)
    └── job       (1:N)
            ├── device   (N:1)
            └── devicelog (1:N)
```

---

## TODO
- [ ] MongoDB 컬렉션으로 구현
- [ ] Prefect flow와 연동 테스트
- [ ] XRD 파일 자동 파싱 후 result에 저장
- [ ] 실험 조건 → 결과 그래프(Knowledge Graph) 변환
