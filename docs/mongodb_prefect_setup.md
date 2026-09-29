# MongoDB + Prefect 연결 가이드 

> 해당 문서는 `imms-sdl-os` 레포를 처음 받은 사람이 자기 컴퓨터에서
> **Prefect 대시보드**와 **MongoDB Atlas**가 실제로 눈에 보이도록
> 16단계 flow(`src/pipeline/live_16step_flow.py`)를 실행하기까지의
> 전체 과정을 담은 가이드입니다. 실제로 겪었던 에러들을 전부 반영했습니다.
>
> 순서대로 따라 하면 됩니다. 각 단계 끝에 "확인" 항목이 있으니
> 그게 안 되면 다음 단계로 넘어가기 전에 하단 트러블슈팅 표를 먼저 참고해주세요. 

---

## 0. 준비 (로컬 pc 셋팅)

- Python 3.10 이상 (3.14 권고)
- imms_sdl 레포에 대한 git 접근 권한
- MongoDB Atlas 프로젝트 접근 권한 (Database Access에 계정이 있어야 함) -> 공유 DB 생성 예정

---

## 1. 레포 클론

```bash
git clone <repo-url>
cd imms-sdl-os
```

이미 다운로드해서 폴더가 있다면 그 폴더로 `cd`만 하면 됩니다.

---

## 2. 패키지 설치

```bash
python3 -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash 기준. macOS/Linux는 source .venv/bin/activate
pip install -r requirements.txt
pip install pyserial
```

> **`pyserial`은 꼭 따로 설치해야 합니다.**
> `requirements.txt`에 빠져 있는 패키지입니다. 저울 드라이버 코드(`src/hardware/balance_mtsics.py`)가
> `import serial`을 쓰는데, pip 패키지 이름은 `pyserial`이고 import 이름은 `serial`이라서 헷갈리지 않도록 유의하시기 바랍니다.
> 이걸 안 깔면 `ModuleNotFoundError: No module named 'serial'` 에러가 발생할 수 있습니다.

**확인:**
```bash
python3 -c "import pydantic, pymongo, prefect, serial; print('전부 설치 완료')"
```
`전부 설치 완료`가 뜨면 성공.

---

## 3. `.env` 파일 만들기 (MongoDB 접속 정보)

레포 최상단(가장 바깥 폴더)에서:

```bash
cp .env.example .env
```

>  **`.env.example`이 아니라 `.env`를 수정해야 합니다.** 코드는 `.env`만 읽습니다.
`.env` 파일을 열어서 아래처럼 실제 값으로 채웁니다:

```
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-name>.mongodb.net/?appName=<app-name>
MONGODB_DB_NAME=imms_sdl_os
```

>  **`<`, `>` 꺾쇠괄호를 전부 지워야 합니다.** `<username>`처럼 꺾쇠까지 그대로 남겨두면
> `The DNS query name does not exist: _mongodb._tcp.<cluster-name>.mongodb.net.` 같은 에러가 발생합니다.
> username, password, cluster-name, app-name 자리에 실제 값을 넣고 `<`/`>`는 전부 삭제하세요.

예시 (실제 클러스터 주소 형식):
```
MONGODB_URI=mongodb+srv://sdl_local:실제비밀번호@siyeong.bb3igip.mongodb.net/?appName=imms-sdl-os
MONGODB_DB_NAME=imms_sdl_os
```

접속 문자열은 MongoDB Atlas 콘솔 → 해당 클러스터 → **Connect** → **Drivers**에서 확인할 수 있습니다.

### 3-1. MongoDB Atlas 계정이 아직 없다면 (Database Access 유저 새로 만들기)

담당자(또는 기존 admin 권한자)가 Atlas 콘솔에서:

1. 좌측 메뉴 **Database Access** → **Add New Database User**
2. Authentication Method: **Password**
3. Username / Password 입력 (이 값을 `.env`의 `<username>`, `<password>` 자리에 넣게 됨)
4. Database User Privileges: **Specific Privileges** 선택 →
   `readWrite` on database `imms_sdl_os`만 부여 ( `atlasAdmin`이나 본인 admin 계정을 재사용하지 말 것 —
   협업자마다 딱 필요한 권한만 준 새 계정을 만들어야 합니다)
5. **Add User**

그리고 **Network Access** 메뉴에서 접속할 컴퓨터의 IP를 허용 목록에 추가합니다
(모르면 일단 `0.0.0.0/0`으로 전체 허용 후, 나중에 좁혀도 됩니다).

**확인:** 아래 4번 단계까지 진행했을 때 ` MongoDB 연결 성공: db='imms_sdl_os'` 로그가 뜨면 성공.

---

## 4. Prefect 서버 띄우기 (전용 터미널 하나 필요)

**새 터미널 창**을 하나 열고, 레포 폴더에서:

```bash
python3 -m prefect server start
```

`command not found` 에러가 나면 (`prefect` 명령이 PATH에 없는 경우) 위처럼 `python3 -m prefect ...`
형태로 실행하면 됩니다 (이 문서의 모든 prefect 명령은 이 방식을 씁니다).

아래처럼 배너가 뜨고 주소가 나오면 성공:
```
Check out the dashboard at http://127.0.0.1:4200
```

> **이 터미널 창은 절대 닫지 마세요.** 서버가 이 프로세스 안에서 돌아가고 있어서,
> 창을 닫으면 서버도 같이 꺼지고 대시보드도 안 열립니다.

**확인:** 브라우저에서 `http://127.0.0.1:4200` 접속 → Flow Runs가 0개인 빈 화면이 뜨면 정상
(아직 아무것도 실행 안 했으니 비어있는 게 맞음).

> 브라우저에서 "failed to load page" / "연결할 수 없음"이 뜬다면:
> - 서버가 실제로 켜져 있는지 위 터미널 창을 확인하세요.
> - 주소를 정확히 `http://127.0.0.1:4200`으로 입력했는지 확인하세요
>   (`https://127/0/0/1:8026`처럼 슬래시나 잘못된 포트로 오타 내는 경우가 있었습니다).

---

## 5. `PREFECT_API_URL` 설정 — **가장 빼먹기 쉬운 단계**

서버를 띄운 터미널은 그대로 두고, **또 다른 새 터미널 창**을 열어서
(flow를 실행할 터미널) 레포 폴더로 이동한 뒤:

```bash
python3 -m prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

**확인:**
```bash
python3 -m prefect config view
```
출력에 `PREFECT_API_URL='http://127.0.0.1:4200/api'`가 보이면 성공.

> **이 단계가 필요한 이유는 다음과 같습니다**
> flow를 실행했을 때 로그에 찍히는 주소가 `http://127.0.0.1:4200`이 아니라
> `8026`, `8886`처럼 엉뚱한 포트로 나옵니다. 이건 Prefect가 "지정된 서버를 못 찾겠으니
> 나 혼자 임시 서버를 새로 띄울게"라고 판단하기 때문입니다 — 그 임시 서버는
> 우리가 보고 있는 `4200` 대시보드가 아니라서, flow는 실제로 실행되지만 대시보드에는
> 아무것도 안 보입니다.
>
> **중요:** 이 설정은 **flow를 실행하는 바로 그 터미널/세션**에서 해줘야 합니다.
> 새 터미널을 열 때마다, 또는 컴퓨터를 재시작했을 때마다 다시 확인하는 게 안전합니다.

---

## 6. flow 실행하기

같은 터미널(5번에서 `PREFECT_API_URL`을 설정한 그 터미널)에서:

```bash
python3 -m src.pipeline.live_16step_flow
```

### 기대되는 정상 출력

```
1) 정상 실행
============================================================
Beginning flow run '...' for flow 'solid-dosing-16step'
View at http://127.0.0.1:4200/runs/flow-run/...
16개 Action 생성 완료 (safety_critical: [7, 14]번)
    [SIM-Action] PICK (#1)
    [SIM-Action] MOUNT (#2)
    ...
실행 완료: 성공 9개 / 실패 7개 (총 16개)
 MongoDB 연결 성공: db='imms_sdl_os'
MongoDB 저장 완료 — task_id=live_dispense_...
Finished in state Completed()

2) 안전장치 시연 (RETRACT 강제 실패)
============================================================
...
ValueError: 안전 순서 위반: ActionType.DOOR_CLOSE(#7)은 이전 Action이 success여야 실행 가능합니다.
...
MongoDB 저장 완료 — task_id=live_dispense_...
Finished in state Completed()
```

> 💡 **"성공 9개 / 실패 7개"는 버그가 아니라 정상입니다.**
> 로봇 관련 9개 Action은 시뮬레이션이라 성공으로 나오고, 저울(balance) 관련 7개 Action은
> 실제 하드웨어가 연결되어 있지 않아서 정직하게 "실패"로 보고하는 겁니다. 이게 바로
> OS가 실제 장비 상태를 있는 그대로 추적한다는 증거예요 — 하드웨어 없이 전부 성공으로
> 위장하는 게 아니라, 없는 건 없다고 정확히 보고하는 설계입니다.
>
> 2번째 실행(안전장치 시연)에서 `ValueError`가 뜨는 것도 의도된 동작입니다.
> RETRACT를 일부러 실패시켜서, 그다음 안전 필수 단계인 DOOR_CLOSE(#7)가 절대
> 실행되지 않고 멈추는지 확인하는 테스트예요.

---

## 7. 결과 확인하기

### 7-1. Prefect 대시보드에서 확인

`http://127.0.0.1:4200` → **Flow Runs** 메뉴에 방금 실행한 2개의 flow run
(랜덤한 이름, 예: `lumpy-nuthatch`, `quixotic-crane`)이 보이면 성공.
각각 클릭하면 Task 단위로 실행 그래프/로그를 볼 수 있습니다.

### 7-2. MongoDB Atlas에서 확인

Atlas 콘솔 → 해당 클러스터 → **Browse Collections** → `imms_sdl_os` 데이터베이스 →
`task` (또는 스키마에 정의된 컬렉션명) 컬렉션에서 방금 생성된 `task_id`
(`live_dispense_20260922_...` 형식)를 검색 → 문서를 열어서 `actions` 배열에
16개 항목이 다 들어있는지 확인.

---

## 8. 트러블슈팅 표

| 증상 (터미널에 뜨는 메시지) | 원인 | 해결 |
|---|---|---|
| `python3: command not found` | Python이 설치 안 됐거나 PATH에 없음 | Python 재설치, 또는 `python`/`py` 명령으로 대체 시도 |
| `python3`만 치고 `>>>` 프롬프트가 뜸 | 파일명 없이 REPL로 진입한 것 | `exit()` 입력 후 `python3 파일명.py`로 다시 실행 |
| `ls` 했을 때 파일명에 `.py`가 빠져 있음 | 업로드/저장 시 확장자 누락 | `mv 파일명 파일명.py`로 이름 변경 |
| `ModuleNotFoundError: No module named 'pydantic'` | 패키지 미설치 | `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'serial'` | `pyserial` 별도 미설치 (requirements.txt에 없음) | `pip install pyserial` |
| `ERROR: Operation cancelled by user` (설치 중) | 설치 도중 실수로 Ctrl+C | 다시 `pip install -r requirements.txt` 실행, 급하면 `pip install pydantic pymongo python-dotenv prefect pyserial`만 우선 설치 |
| `MONGODB_URI가 설정되지 않았습니다` | `.env` 파일 자체가 없음 | `cp .env.example .env` 후 값 채우기 |
| `The DNS query name does not exist: _mongodb._tcp.<cluster-name>...` | `.env`에 `<`/`>` 꺾쇠가 그대로 남아있음 | `.env`에서 `<`, `>` 전부 삭제하고 실제 값으로 교체 |
| 브라우저에서 "failed to load page" / 접속 안 됨 | Prefect 서버 자체가 안 켜져 있거나 URL 오타 | `python3 -m prefect server start` 창이 살아있는지 확인, 주소는 정확히 `http://127.0.0.1:4200` |
| `httpx.ConnectError: [WinError 10061] 대상 컴퓨터에서 연결을 거부했으므로...` / `Failed to reach API at http://127.0.0.1:4200/api/` | Prefect 서버가 실행 중이 아닌 상태에서 flow를 실행함 | 서버용 터미널에서 `python3 -m prefect server start` 먼저 실행하고, 그 창을 켜둔 채로 flow 실행 |
| flow 실행 로그에 `View at http://127.0.0.1:8026/...` 또는 `:8886/...`처럼 4200이 아닌 다른 포트가 나옴 | `PREFECT_API_URL`을 설정 안 해서 Prefect가 임시 서버를 새로 띄움 (대시보드에 안 보임) | flow를 실행할 그 터미널에서 `python3 -m prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api` 실행 후 `python3 -m prefect config view`로 확인, 그 다음 다시 flow 실행 |
| `git add` 시 `did not match any files` | 파일이 아직 원하는 경로로 이동/생성되지 않음 | `ls`로 실제 위치 확인 후 `mv`로 옮기고 다시 `git add` |
| `git commit` 시 `Author identity unknown` | git 사용자 정보 미설정 | `git config --global user.email "본인이메일"` / `git config --global user.name "본인이름"` |
| `git push` 시 `[rejected] main -> main (fetch first)` | 다른 사람이 먼저 push함 | `git pull` 후 `git push` |
| `git pull` 시 Vim 편집기가 갑자기 뜸 (`MERGE_MSG` 화면) | 자동 병합 커밋 메시지를 작성하라고 에디터가 열린 것 | `Esc` 누르고 `:wq` 입력 후 `Enter` (저장하고 종료) |

---

## 참고: 이 flow가 하는 일 요약

- `src/pipeline/live_16step_flow.py`는 고체 분주(Solid Dosing) 16단계 워크플로우를
  실제 Prefect `@flow`/`@task`로 감싸서, 실행되는 순간 Prefect 대시보드와
  MongoDB에 동시에 기록되도록 만든 코드입니다.
- 로봇(PICK/PLACE/RETRACT/MOUNT 등)과 저울(DOSE 등) 제어는 아직 실제 하드웨어
  드라이버가 없어서 시뮬레이션(`_simulated_driver`)으로 동작합니다. 실제 로봇 코드가
  준비되면 `register_action_driver()` 한 줄로 시뮬레이션 → 실제 실행 전환이 가능하도록
  설계되어 있습니다 (Task/Prefect flow 코드 자체는 수정할 필요 없음).
- 16단계 중 7번, 14번(DOOR_CLOSE)은 `safety_critical`로 지정되어 있어서, 직전
  RETRACT가 실패하면 절대 실행되지 않고 `ValueError`로 멈춥니다 — 이게 이 flow가
  증명하는 핵심 안전장치입니다.
