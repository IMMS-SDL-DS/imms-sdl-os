# 🧪 IMMS SDL-OS — Self-Driving Laboratory Operating System

> **이화여자대학교 IMMS (Institute for Multiscale Materials and Systems)**  
> 국가연구소(NRL 2.0) 학부 인턴 연구 기록  
> 연구자: [이름] | 소속: 데이터사이언스학과 | 기간: 2025.07 – 2025.08

---

## 🔬 연구 개요

MOF(Metal-Organic Framework) 자율실험실(SDL)의 **운영체제(OS) 구축**을 위한  
데이터베이스 시스템 및 파이프라인 자동화 연구.

실험 장비에서 생성되는 데이터를 AI가 학습할 수 있는 형태로  
자동 수집·정제·저장하는 **Prefect 기반 워크플로우 파이프라인**을 설계하고,  
실제 장치와 연결하는 것을 목표로 한다.

---

## 🏗️ 프로젝트 구조

```
imms-sdl-os/
│
├── src/
│   ├── pipeline/        # Prefect 워크플로우 정의
│   ├── database/        # DB 스키마 및 연결 모듈
│   └── device/          # 실험 장치 연결 인터페이스
│
├── notebooks/           # 탐색적 분석 및 실험 노트북
├── data/
│   └── schema/          # DB 스키마 정의 파일
├── docs/                # 연구 문서 및 학습 노트
├── tests/               # 유닛 테스트
└── logs/                # 실험 로그 (gitignore)
```

---

## 🛠️ 기술 스택

| 분야 | 기술 |
|------|------|
| 워크플로우 자동화 | [Prefect](https://www.prefect.io/) |
| 데이터베이스 | MongoDB / PostgreSQL |
| 언어 | Python 3.11+ |
| 장치 통신 | SiLA2 / REST API |
| 참고 구조 | AlabOS, ChemOS 2.0 |

---

## 📚 핵심 참고 논문

| 논문 | 설명 |
|------|------|
| [AlabOS (Fei et al., 2024)](https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00129j) | Python 기반 재설정 가능한 워크플로우 관리 프레임워크 |
| [ChemOS 2.0 (Sim et al., 2024)](https://www.sciencedirect.com/science/article/pii/S2590238524001954) | 실험실을 OS로 보는 오케스트레이션 아키텍처 |
| [IvoryOS (2025)](https://www.nature.com/articles/s41467-025-60514-w) | Python SDL용 상호운용 가능한 자동 웹 인터페이스 |
| [UniLabOS (2025)](https://arxiv.org/abs/2512.21766) | AI-Native 자율실험실 OS |
| [Tom et al., Chem. Rev. 2024](https://pubs.acs.org/doi/full/10.1021/acs.chemrev.4c00055) | SDL 종합 리뷰 |

---

## 📅 연구 진행 기록

진행 상황은 [docs/progress.md](docs/progress.md) 참고.

---

## 🔗 관련 기관

- [IMMS 공식 사이트](https://sites.google.com/view/i-imms-2026)
- [나종걸 교수 연구실](https://nagroup.ewha.ac.kr/)
- 이화여자대학교 화공신소재공학과
