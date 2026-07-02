# 📅 연구 진행 기록

> 매주 배운 것, 만든 것, 막혔던 것을 모두 기록!! 일종의 TROUBLE SHOOTING 
---

## Day 1 — 사전 준비 (2026.7.1)

### 읽은 논문
- [x] AlabOS (Fei et al., 2024) — Digital Discovery

### 정리 메모
> AlabOS 핵심 요약
- 자율실험실 = Sample / Device / Task / Experiment 4가지로 구성
- 실험 순서 = DAG (Prefect의 Flow 구조랑 동일!)
- Resource Manager = 장비 충돌 방지 핵심
- MongoDB로 모든 상태 실시간 추적
- A-Lab 1.5년 3,500샘플 실증 → 우리가 만들 시스템의 교과서

> 느낀 점
- Prefect의 @flow / @task 구조가 AlabOS의 Experiment / Task 구조와
  거의 동일하다는 걸 깨달음. 논문을 먼저 읽고 Prefect를 배우니
  왜 이런 구조인지 이해가 훨씬 빠름
- MOF 실험에서 Sample = MOF 샘플, Device = XRD 장비,
  Task = XRD 측정 작업으로 바로 매핑 가능
---

## Day 2 — (2026.7.2)

### 읽은 논문
- [x] ChemOS 2.0 (Sim et al., 2024) — Matter
- [x] IvoryOS (2025) — Nature Communications

### 배운 것
> ChemOS 2.0 핵심 요약
- 실험실 = OS (UNIX 철학: 모듈화·연동·JSON 통신)
- DB 구조: device/job/devicelog 공통 + 장비별 특화 테이블
- SiLA2로 모든 장비 통신 표준화 → 새 장비 추가가 쉬워짐
- Atlas BO 내장 → AI가 다음 실험 조건 자동 제안
- 점진적 도입 가능 → 장비 하나씩 붙여나가는 전략

### 깨달은 점
> - AlabOS의 DAG 구조 + ChemOS 2.0의 표준화된 DB 설계를
  Prefect로 구현하는 게 해당 연구실에서 내 역할의 핵심
- device/job/devicelog 세 테이블이 핵심 뼈대
  → MOF XRD 실험에 맞게 변형하는 게 첫 번째 과제구나...

---

## Day 3 — (2026.7.3)

### 읽은 논문
- [x] UniLabOS (2025) — arXiv
- [x] Tom et al. SDL 리뷰 (2024) — Chemical Reviews

### 배운 것
-

### 막혔던 것 & 해결
-

### 더 해볼 것
- [ ] Prefect 설치 후 example_flow.py 실행
- [ ] MongoDB vs PostgreSQL 어떤 게 우리 연구에 맞는지 검토
- [ ] MOF 실험용 device/job/devicelog 스키마 초안 작성

---

<!-- 이하 동일 형식으로 주차별 추가 -->
