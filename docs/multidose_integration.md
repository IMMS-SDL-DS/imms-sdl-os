# MultiDose 실증 — 로봇 제어 인터페이스 계약

> 교수님 요청(2026.7): OS의 첫 실증으로 MultiDose(로봇팔+저울 고체 분주 시스템)를
> 사용해서, "어떤 소재를 몇 그램 담아라"는 일반화된 명령이 그대로 실행되게 만들기.
> 역할: 로봇/저울 제어 = 김연서·안윤수, 도징헤드 판 = 정윤서, OS 레이어 = 손시영.

## 지금 만들어둔 것

`src/pipeline/dispense_command.py` — 범용 명령 인터페이스:
```python
run_dispense_command(reagent="ZrOCl2", target_mass_mg=97, vessel="Vial_10mL")
```
이 함수 하나가:
1. 파라미터를 검증하고 (Pydantic, `src/database/models.py`)
2. 로봇 드라이버 함수를 호출하고
3. 결과를 MongoDB에 Task/Sample로 기록한다

지금은 `simulated_robot_driver`(가짜 실행)가 꽂혀 있음. 실제 MultiDose 제어 코드로
교체하기만 하면 그대로 실증에 쓸 수 있음.

## 김연서·안윤수와 맞춰야 할 인터페이스 계약

로봇 제어 함수가 아래 시그니처를 따르면, `dispense_command.py`는 코드 수정 없이
`robot_driver=실제함수` 인자만 바꿔 끼우면 바로 연동됨.

```python
def 실제_robot_driver(
    reagent: str,        # 시약명 (예: "ZrOCl2")
    target_mass_mg: float,   # 목표 질량 (mg)
    tolerance_mg: float,     # 허용 오차 (mg)
    vessel: str,          # 담을 용기 (예: "Vial_10mL")
) -> dict:
    ...
    return {
        "actual_mass_mg": float,  # 실제로 분주된 질량
        "success": bool,          # tolerance 이내로 성공했는지
    }
```

## 만나서 확인할 질문 리스트

1. **로봇/저울 제어 코드가 이미 Python으로 작성돼 있나요?**
   - Python이면: 함수를 그대로 import해서 `robot_driver` 자리에 넣으면 됨
   - 별도 프로그램/프로세스로 떠 있으면: 소켓/HTTP API로 통신해야 함 (→ 통신 방식 확인 필요)

2. **MultiDose 자체 소프트웨어(제조사 제공)를 그대로 쓰나요, 아니면 UR 로봇 SDK로 직접 제어하나요?**
   - MultiDose가 자체 UI/소프트웨어 중심이라, 외부 스크립팅이 안 될 수도 있음
   - 안 되면 → UR3e robot API + Mettler Toledo XPR 저울 API를 따로 붙이는 방식이어야 함

3. **위 4개 인터페이스 필드(reagent, target_mass_mg, tolerance_mg, vessel)로 실제 실행에 충분한가요?**
   - 도징헤드(정윤서 담당) 위치 지정이 추가로 필요할 수도 있음 (예: `dosing_head_id`)

4. **실행 결과를 어떤 형태로 돌려받을 수 있나요?**
   - 실측 질량, 성공 여부 외에 로그 파일 경로, 타임스탬프 등 추가로 필요한 정보가 있는지

## 다음 단계

- [ ] 위 질문 답변 받아서 실제 `robot_driver` 함수 구현
- [ ] `dispense_command.py`의 `simulated_robot_driver`를 실제 함수로 교체
- [ ] Device 컬렉션에 `dev_multidose` 실제 정보 등록 (device_type, connection 등)
- [ ] 실제 MultiDose로 최소 1회 end-to-end 실증 (명령 → 실행 → DB 기록 확인)
