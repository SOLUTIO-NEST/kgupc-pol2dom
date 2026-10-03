# kgupc-pol2dom

KGUPC 운영진을 위한 **Polygon → 한글 문제 PDF → DOMjudge 연동 도구**입니다. Polygon에서 작성한 지문에 kgupc-toolkit의 템플릿을 적용하고, 테스트 케이스·채점기·정답 코드·제한과 함께 DOMjudge로 이전합니다. 별도 웹서비스 없이 운영진 PC에서 명령을 실행합니다.

TeX 환경과 프로그램을 설치한 뒤 `.env`에 접속 정보·대회명·날짜·폴더명을 채우면, 평소에는 아래 **한 명령**을 사용합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom deploy --build-packages
```

이 명령은 Polygon 다운로드 → 통합·개별 한글 PDF 생성 → Git에서 제외된 `build/archive/<CONTEST_SLUG>/`에 편집 가능한 대회 폴더 생성 → DOMjudge 문제 연동까지 실행합니다. 대회 종료 후에는 생성된 `<CONTEST_SLUG>` 폴더를 archive에 직접 복사하면 됩니다.

평소 작업 흐름은 다음과 같습니다.

1. Polygon에서 문제를 작성하거나 수정하고 커밋합니다.
2. 이 도구로 PDF와 문제 패키지를 만들고 검토합니다.
3. 지정한 DOMjudge 대회에 연동합니다. 이후 수정도 같은 명령으로 반영합니다.

이 저장소에는 프로그램과 공개용 예제만 보관합니다. **실제 대회 자료는 Polygon과 운영진의 로컬 작업 폴더에 보관합니다.** 종료 후 공개할 폴더도 로컬에서만 생성하며 Git에서 제외합니다.

| 프로젝트 | 담당하는 일 |
| --- | --- |
| [kgupc-toolkit](https://github.com/SOLUTIO-NEST/kgupc-toolkit) | 템플릿과 PDF 빌드. 전달받은 지문·해설을 조판합니다. |
| kgupc-pol2dom | Polygon 다운로드, toolkit을 통한 PDF 생성, DOMjudge 연동, 복사용 대회 폴더 내보내기. archive 경로나 접근 권한은 필요하지 않습니다. |
| [kgupc-archive](https://github.com/KGU-SOLUTIO/kgupc-archive) | 종료된 대회의 편집 가능한 `.tex`·이미지·예제·PDF와 템플릿 lock을 보관합니다. 운영자가 내보낸 폴더를 직접 복사하고 공개합니다. |

pol2dom은 archive 저장소를 찾아가거나 그 안의 대회 파일을 갱신하지 않습니다. archive에서 지문·해설을 수정하고 다시 PDF를 만드는 작업은 toolkit을 사용하는 archive의 빌드로 진행합니다.

## 1. 처음 사용하는 PC에 설치하기

다음 프로그램이 필요합니다.

- Python 3.10 이상
- Git
- XeLaTeX, latexmk, 한글 조판 패키지 kotex를 포함한 TeX 환경

TeX 환경은 [TeX Live](https://tug.org/texlive/) 등으로 설치합니다. 설치 후 새 터미널에서 `python --version`, `git --version`, `xelatex --version`, `latexmk -v`가 실행되는지 확인합니다.

Windows PowerShell에서 아래 명령을 실행합니다. 이미 저장소가 있다면 해당 폴더에서 가상환경 생성부터 진행합니다.

```powershell
git clone https://github.com/SOLUTIO-NEST/kgupc-pol2dom.git
cd kgupc-pol2dom
python -m venv .venv
.venv/Scripts/python -m pip install "kgupc-toolkit @ git+https://github.com/SOLUTIO-NEST/kgupc-toolkit.git@373249973347711ef7aaed1283aa328ae3c23b66"
.venv/Scripts/python -m pip install .
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

이후 명령도 **이 저장소 폴더에서** 실행합니다. 가상환경을 따로 활성화할 필요는 없습니다. Linux/macOS에서는 `.venv/Scripts/python` 대신 `.venv/bin/python`을 사용합니다. 프로그램 소스를 업데이트했다면 `.venv/Scripts/python -m pip install .`을 다시 실행합니다.

위 설치 명령은 toolkit을 정확한 커밋에 고정합니다. 대회 준비 중에는 담당자들이 같은 커밋을 사용하고, 대회별로 다른 템플릿이 필요하면 가상환경을 나눕니다. 생성 결과의 `toolkit.lock.json`에도 설치된 버전과 내용 해시가 기록됩니다.

## 2. Polygon과 DOMjudge 접속 정보 설정하기

`.env.example`을 복사해 만든 `.env`를 편집합니다. 아래 값은 모두 예시이며 실제 대회 정보로 바꿉니다.

```dotenv
POLYGON_API_KEY=your_api_key
POLYGON_API_SECRET=your_api_secret
POLYGON_CONTEST_URL=https://polygon.codeforces.com/contest?contestId=12345

CONTEST_SLUG=2026-fall
CONTEST_TITLE="KGUPC 2026 Fall"
CONTEST_DATE=2026-10-29
CONTEST_AUTHOR="Solutio in Kyonggi Univ."

DOMJUDGE_URL=https://judge.example.com/domjudge
DOMJUDGE_USERNAME=your_admin_username
DOMJUDGE_PASSWORD=your_admin_password
DOMJUDGE_CONTEST_ID=kgupc-2026-fall
```

| 설정 | 어디서 확인하나요? |
| --- | --- |
| `POLYGON_API_KEY`, `POLYGON_API_SECRET` | Polygon의 Settings에서 발급합니다. 해당 계정에 대회와 각 문제의 접근 권한이 있어야 합니다. |
| `POLYGON_CONTEST_URL` | 가져올 Polygon 대회의 주소를 복사합니다. 코드에 대회 ID를 적을 필요가 없습니다. |
| `CONTEST_SLUG` | 복사용 대회 폴더 이름입니다. 예: `2025`, `2026-spring`, `2026-fall`. 전체 `bundle`·`deploy`에 필요합니다. |
| `CONTEST_TITLE` | PDF 표지와 문제 페이지 머리말에 표시할 대회명입니다. API ID나 폴더 이름과는 별개입니다. |
| `CONTEST_DATE` | 표지에 표시할 날짜입니다. `YYYY-MM-DD`로 적고, 표시하지 않으려면 비웁니다. |
| `CONTEST_AUTHOR` | 표지의 작성자·주최 동아리 이름입니다. |
| `DOMJUDGE_URL` | DOMjudge 접속 주소입니다. `/domjudge` 같은 설치 경로가 있으면 포함합니다. `/api/v4` 주소도 사용할 수 있습니다. |
| `DOMJUDGE_USERNAME`, `DOMJUDGE_PASSWORD` | 서버 담당자에게 받은 **admin 역할** 계정입니다. 별도 API 키가 아니라 계정 이름과 비밀번호로 인증합니다. |
| `DOMJUDGE_CONTEST_ID` | 아래 대회 목록 조회 결과의 `contests[].id`를 사용합니다. Polygon 대회 ID와는 별개입니다. |

Polygon에서 API PIN을 요구하면 `POLYGON_PIN`도 추가합니다. 공유 링크의 `ccid`는 API PIN이 아닙니다. 비밀번호에 `#`이나 공백이 있으면 `DOMJUDGE_PASSWORD="your password#here"`처럼 따옴표로 감쌉니다.

`.env`는 Git에서 제외됩니다. 인증 정보나 비공개 대회 링크를 README·소스·커밋에 넣지 않습니다. 대회가 여러 개라면 로컬 환경 파일을 나누고, 명령마다 `--env-file C:/private/2026-fall.env`를 지정할 수 있습니다.

설정 우선순위는 **프로세스 환경변수 → `.env` → Windows 사용자 환경변수**입니다. 예전 대회를 계속 조회한다면 환경변수에 이전 URL이 남아 있는지도 확인합니다.

PDF 정보는 `prepare`·`bundle`·`deploy` 실행 시 읽어서 생성하는 `main.tex`에 반영합니다. 설정이 없으면 대회명 `KGUPC`, 작성자 `Solutio in Kyonggi Univ.`, 빈 날짜를 사용합니다. 값은 일반 텍스트이며 TeX 명령을 적지 않습니다. `&`, `%`, `_` 등은 자동으로 처리합니다.

`.env` 변경만으로 이미 만들어진 PDF나 DOMjudge에 업로드된 PDF가 바뀌지는 않습니다. 새 `bundle` 또는 `deploy`를 실행하면 변경한 정보로 생성됩니다. `upload`·`export-archive`는 선택한 bundle을 그대로 사용하므로 그 이후 `.env` 변경의 영향을 받지 않습니다. 기본 복사용 폴더 이름은 `CONTEST_SLUG`이고, 과거 bundle을 별도로 내보낼 때만 `export-archive --name`을 사용합니다.

### DOMjudge 대회 ID 확인

DOMjudge에는 대회·계정·judgehost가 미리 준비되어 있어야 합니다. 이 도구는 문제를 연동하며, 대회 생성이나 일정 설정·참가자 공개는 수행하지 않습니다. 처음 연결할 때는 별도의 테스트 대회를 사용합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom domjudge-list
```

출력된 대회 목록에서 대상 대회를 찾고 **`id` 값**을 `.env`의 `DOMJUDGE_CONTEST_ID`에 넣습니다. 관리 화면의 항목은 다음처럼 구분합니다.

| 관리 화면 항목 | 의미 | `.env`에 사용하나요? |
| --- | --- | --- |
| Contest ID | 서버 내부의 숫자 ID. 예: `1` | 아니요. 숫자로 추측하지 않습니다. |
| External ID | API에서 사용하는 대회 ID. 예: `kgupc-2026-fall` | 네. 목록 조회의 `id`로 확인합니다. |
| Shortname / Name | 화면에 표시할 대회 이름 | 아니요. 이름만 변경하면 `.env`를 바꿀 필요가 없습니다. |

**External ID는 첫 연동 전에 정하고 유지해 주세요.** 현재 문제 식별에도 이 값이 사용됩니다. External ID를 바꾸면 `.env`를 수정하고 패키지를 다시 생성해야 하며, 기존 문제를 같은 ID로 갱신하는 흐름도 달라집니다. 표시 이름을 바꾸려면 Shortname / Name을 사용합니다.

## 3. Polygon에서 문제 준비하기

먼저 `.env`가 원하는 대회를 가리키는지 확인합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom polygon-list
```

Polygon에서는 한글 지문을 `korean` 언어로 작성하고, 예제에 사용할 테스트와 예제 정답을 준비합니다. 테스트 케이스·채점기·정답 코드·시간 및 메모리 제한도 확인한 뒤 **변경 사항을 커밋합니다.** 도구가 대신 커밋하지 않으며, 미커밋 수정본은 DOMjudge에 배포하지 않습니다.

배포에는 현재 커밋 revision에 맞는 **Linux Full 패키지**가 필요합니다. 아래 명령의 `--build-packages`는 필요한 패키지가 없을 때 Polygon에 검증을 포함한 빌드를 요청하고 기다립니다. 이 경우 Polygon의 문제 쓰기 권한이 필요합니다. 직접 Packages에서 해당 Full 패키지를 만들어 두었다면 이 옵션을 생략할 수 있습니다. 오래된 패키지와 현재 지문을 섞어서 배포하지 않습니다.

현재 지원 범위는 **표준 입출력을 사용하는 단일 패스 일반 문제**입니다. 인터랙티브·멀티패스·파일 입출력 문제의 배포는 지원하지 않습니다. 기본 언어와 테스트셋은 각각 `korean`, `tests`이며, 다른 설정은 `--language`, `--testset`으로 지정합니다.

## 4. PDF를 검토한 뒤 DOMjudge에 올리기

### 처음 연동하거나 대회 직전 최종본을 확인할 때

먼저 서버에 올리지 않고 결과물을 만듭니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom bundle --build-packages
```

명령이 출력한 실행 폴더 또는 `build/archive/<CONTEST_SLUG>/problems/`에서 통합 PDF와 각 문제의 PDF를 열어 지문·이미지·예제·제한을 확인합니다. 전체 `bundle`도 복사용 폴더를 자동 생성하지만 DOMjudge 서버는 변경하지 않습니다. 문제 ID를 대상 대회에 맞춰 생성하므로 `DOMJUDGE_CONTEST_ID`는 설정되어 있어야 합니다.

검토한 **동일한 실행 폴더**를 지정해 업로드합니다. 아래 경로는 예시이므로 명령이 출력한 실제 경로로 바꿉니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom upload "C:/Users/me/kgupc-work/deploy-12345/runs/실행-ID"
```

`upload`는 Polygon을 다시 가져오지 않고 이미 만든 결과물을 올립니다. `.env`에는 해당 결과물과 같은 Polygon 대회 URL 및 DOMjudge 접속 정보가 있어야 합니다. 다른 DOMjudge 대회에 연결된 결과물은 업로드가 거부됩니다.

### 다운로드부터 연동까지 한 번에 실행하기

연결과 PDF를 확인했다면 다음 명령으로 전체 과정을 실행할 수 있습니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom deploy --build-packages
```

이 명령은 Polygon 자료 다운로드 → 한글 PDF 생성 → 채점용 ZIP 변환 → 로컬 복사용 폴더 생성 → DOMjudge 연동 순서로 실행합니다. 모든 문제의 PDF와 ZIP 생성·검증, 로컬 내보내기가 끝난 뒤 서버 반영을 시작합니다. 같은 대회를 다시 실행하면 기존 복사용 폴더를 `build/archive/history/`에 백업하고 현재 폴더를 갱신합니다.

**전체 연동은 지정한 DOMjudge 대회의 문제 목록을 Polygon에 맞춥니다.**

- 같은 Polygon 문제는 기존 DOMjudge 문제의 지문·테스트·채점기·제한을 갱신합니다.
- 새 문제는 추가하고, 문제 번호는 Polygon의 A/B/C 등을 그대로 사용합니다.
- Polygon에 없는 기존 문제는 대상 대회에서 연결을 제거합니다. 같은 번호에 다른 문제가 있으면 Polygon 문제로 교체합니다.
- 전역 문제 삭제나 다른 대회의 연결 삭제를 수행하지 않습니다.

특정 문제만 반영하려면 번호를 지정합니다. **부분 연동은 선택하지 않은 문제를 유지합니다.**

부분 `bundle`·`deploy`는 전체 대회 복사용 폴더를 갱신하지 않습니다. 공개할 전체 최종본은 `--letters` 없이 전체 명령으로 만듭니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom deploy --letters A B --build-packages
```

수정 후에도 Polygon에서 커밋하고 위 명령을 다시 실행하면 됩니다. 같은 대상 대회와 Polygon 문제 ID를 유지하면 작업 폴더가 바뀌어도 기존 문제를 갱신합니다. 실행할 때마다 접두사를 덧붙이거나 새로운 문제 ID를 만들지 않습니다.

서버 반영은 문제별로 진행됩니다. 중간에 실패하면 일부 문제만 반영되었을 수 있으므로 오류를 해결한 뒤 **같은 실행 폴더로 `upload`를 다시 실행**합니다. 전체 실행이 끝났을 때 문제 목록이 Polygon과 일치하는지 확인합니다.

### 업로드 후 확인

DOMjudge 관리 화면에서 문제 번호·이름·제한·테스트 수와 내려받은 PDF를 확인합니다. 이어서 jury solution을 실제로 채점해 정답·오답 판정이 정상인지 확인합니다. **ZIP 업로드 성공만으로 실제 채점까지 확인된 것은 아닙니다.**

정답 코드는 문제 ZIP에 포함됩니다. 자동 제출에는 업로드 계정의 팀 연결과 대회 설정이 필요합니다. 팀 연결이 없다는 경고가 나오면 서버 담당자에게 계정 설정을 요청하고, judgehost 및 Judging Verifier에서도 결과를 확인합니다.

## 생성 파일은 어디에 있나요?

기본 작업 폴더는 사용자 홈의 `kgupc-work/deploy-<Polygon 대회 ID>/`입니다. 실행마다 별도 폴더를 만들므로 검토·업로드한 결과물을 보관할 수 있습니다.

```text
kgupc-work/deploy-12345/
  latest.json                 # 마지막으로 변환이 완료된 실행 정보
  domjudge-receipt.json        # 업로드 기록
  runs/<실행-ID>/
    deployment.json           # 원본 revision, 패키지 ID, 테스트 수와 파일 해시
    toolkit.lock.json         # 사용한 PDF 템플릿 버전과 내용 해시
    polygon-import.json       # Polygon 문제 ID와 문제 번호 대응표
    polygon-packages/A.zip    # 원본 Linux Full 패키지
    domjudge-packages/A.zip    # DOMjudge에 올릴 채점 데이터와 PDF
    problems/main.pdf         # 통합 문제집
    problems/A/               # 분리된 지문·이미지·예제와 개별 PDF
```

통합 PDF는 로컬에 보관하고, DOMjudge에는 각 문제의 개별 PDF를 넣습니다. 표시용 예제 입력·출력은 PDF에 적용하며, 채점용 입력과 정답은 원본 패키지와 비교해 보존합니다. `latest.json`은 변환 완료 기록이므로 서버 업로드 성공 여부는 별도로 확인합니다.

`prepare`·`bundle`·`deploy`의 다운로드·배포 작업 폴더는 `--output C:/private/2026-fall`로 바꿀 수 있으며 **모든 Git 작업 트리 밖**에 둡니다. 전체 `bundle`·`deploy`는 복사용 지문·PDF를 pol2dom의 Git에서 제외된 `build/archive/<CONTEST_SLUG>/`에도 자동 생성합니다. 채점용 전체 테스트와 인증 정보는 복사용 폴더에 넣지 않습니다. 어느 명령도 Git commit/push를 수행하지 않습니다.

## DOMjudge 없이 지문 PDF만 확인하기

지문 작성 중에는 Polygon 설정만으로 PDF를 생성할 수 있습니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom prepare --render
```

기본 출력은 `~/kgupc-work/contest-<Polygon 대회 ID>/`입니다. 이미 가져온 문제를 갱신할 때는 다음을 실행합니다. 교체 전 문제 폴더는 작업 폴더의 `build/polygon-backups/`에 백업합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom prepare --replace --render
```

미커밋 지문을 미리 보고 싶다면 `prepare`에 `--working-copy`를 추가할 수 있습니다. 이 옵션은 배포 명령에서는 사용할 수 없습니다.

지문은 `statement-sections/korean/`의 `legend.tex`, `input.tex`, `output.tex`, `notes.tex` 등으로 나뉩니다. 로컬에서 직접 수정한 내용은 Polygon에 자동으로 돌아가지 않으며, 다음 가져오기에서 교체될 수 있습니다. 대회 준비 중 최종 지문은 Polygon에서 관리합니다.

`prepare --replace --render`에서도 `.env`에 명시한 PDF 정보를 갱신합니다. 명시하지 않은 항목과 표지의 다른 로컬 편집은 유지합니다. `deploy`는 별도 실행 폴더를 만들고 `.env`를 기준으로 표지를 생성하므로 준비 폴더의 직접 편집을 자동으로 이어받지는 않습니다. 로컬 수정본을 다시 렌더링할 때는 다음처럼 실행합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom render "C:/private/2026-fall/problems/main.tex" --toolkit-lock "C:/private/2026-fall/toolkit.lock.json"
```

## 대회 종료 후 아카이브에 공개하기

**전체 `deploy`로 독립 대회 폴더 생성과 DOMjudge 연동 → 대회 종료 후 운영자가 archive에 복사 → 검토 후 commit/push** 순서입니다. archive에 빈 대회 구조를 미리 만들거나, 두 저장소의 상대 경로를 설정할 필요가 없습니다.

일반적으로 추가 명령 없이 이미 만들어진 **`build/archive/<CONTEST_SLUG>/` 폴더를 복사**하면 됩니다. 현재 폴더는 마지막으로 로컬 생성이 완료된 전체 실행의 결과입니다. 이후 DOMjudge 업로드가 실패했다면 명령의 오류와 실제 서버 상태도 확인합니다.

대회가 끝나면 **실제 최종 연동에 사용한 전체 bundle의 실행 폴더**를 선택합니다. `--letters`로 일부만 만든 bundle은 내보낼 수 없습니다. 문제를 하나씩 수정해 부분 연동했다면, 대회 최종 상태에서 전체 `bundle`도 만들어 검토·보관해 주세요. `latest.json`은 변환 완료만 뜻하므로 실제 업로드한 최종본인지는 운영자가 확인해야 합니다.

과거의 특정 최종 bundle을 다시 내보내거나 다른 위치에 보관할 때는 아래 별도 명령을 사용할 수 있습니다. 경로는 실제 최종 실행 폴더로 바꿉니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom export-archive "C:/Users/me/kgupc-work/deploy-12345/runs/최종-실행-ID" --name 2026-fall
```

결과는 다음과 같습니다.

```text
kgupc-pol2dom/build/archive/2026-fall/
  toolkit.lock.json
  requirements.txt
  archive-source.json          # 원본 문제 ID·revision과 내보낸 파일 해시
  problems/
    main.tex
    main.pdf
    problem-list.tex
    A/
      <문제 이름>.tex
      <문제 이름>.pdf
      statement.json
      polygon-source.json
      statement-sections/korean/
        name.tex, legend.tex, input.tex, output.tex, notes.tex, ...
        예제 파일·이미지
    B/ ...
```

**`2026-fall` 폴더 자체를 archive 저장소 루트로 복사**하면 `kgupc-archive/2026-fall/`이 됩니다. 파일 탐색기로 복사하시면 됩니다. 같은 이름의 대회가 이미 있다면 기존 지문과 비교하고 필요한 파일만 직접 반영합니다. 기존 2025 교정본을 Polygon 자료로 덮어쓸 필요는 없습니다.

`export-archive`는 선택한 로컬 bundle의 `.tex`·리소스·예제·PDF·lock을 그대로 복사합니다. **Polygon 재조회, DOMjudge 접속, PDF 재생성, archive 접근을 하지 않으며 `.env`도 읽지 않습니다.** API 키·비밀번호·채점용 전체 테스트·문제 ZIP·빌드 중간 파일은 출력에 포함하지 않습니다. 실제 사용한 실행 폴더를 이후 직접 수정하지 말고 보관해 주세요. DOMjudge에서 별도로 수정한 내용은 이 로컬 bundle에 자동으로 돌아오지 않습니다.

출력과 이전 출력 백업은 `.gitignore`의 `build/` 규칙으로 제외됩니다. Git 저장소 안에서는 pol2dom의 `build/archive/`만 허용하고, 무시되지 않거나 이미 추적 중인 출력은 거부합니다. 별도 `export-archive`에서 `--output C:/private/handoff`를 지정하면 그 아래 `2026-fall/`이 생성됩니다. 이 별도 명령은 기존 폴더를 덮어쓰지 않습니다. 전체 `bundle`·`deploy`만 같은 Polygon 대회의 생성 폴더를 백업하고 갱신하며, 다른 대회나 출처 기록이 없는 기존 폴더는 교체하지 않습니다.

복사 후 필요한 제목·날짜 수정은 `problems/main.tex`에서 진행합니다. 표지는 bundle 생성 시 `.env`에 설정했던 정보를 유지합니다. 해설 슬라이드는 자동으로 생성하지 않습니다. archive에서 `solutions/`에 작성하거나 기존 해설을 추가합니다. toolkit 설치 환경인 `.venv`도 복사하지 않으므로 archive의 안내에 따라 해당 lock에 맞는 환경을 준비한 뒤 다시 빌드합니다. `requirements.txt`의 버전 번호만 같아도 내용 해시가 다를 수 있으므로 대회에 사용한 toolkit 커밋 또는 wheel도 보관합니다.

**공개 시점은 운영진이 결정합니다.** 대회가 종료되고 공개해도 되는지, 최종 지문이 맞는지 확인한 뒤 archive에서 직접 commit/push합니다. 기존에 archive를 직접 갱신하던 `archive-import` 명령은 제거했습니다.

## 문제가 생겼을 때

| 증상 | 확인할 내용 |
| --- | --- |
| `python`, `xelatex`, `latexmk`를 찾지 못함 | 해당 프로그램과 PATH를 확인하고 새 터미널을 엽니다. Python 실행은 저장소의 가상환경 경로를 사용합니다. |
| Polygon 인증·권한 오류 | API key/secret, 계정의 대회·문제 접근 권한을 확인합니다. 자동 Full 패키지 빌드에는 쓰기 권한도 필요합니다. |
| 수정본이 배포되지 않음 | Polygon에서 커밋했는지 확인합니다. 오래된 Full 패키지라면 `--build-packages`로 다시 생성합니다. |
| Polygon 패키지 빌드 실패 | Polygon Packages의 검증 로그에서 테스트·정답·validator 오류를 해결합니다. |
| DOMjudge 401/403 오류 | URL의 설치 경로, 계정 이름·비밀번호, admin 역할을 확인합니다. |
| 대회를 찾지 못함 | `domjudge-list`의 `contests[].id`를 사용합니다. 내부 숫자 ID나 화면의 이름으로 추측하지 않습니다. |
| 다른 대회 결과물이라며 업로드 거부 | 환경 파일과 실행 폴더를 확인합니다. 대상 대회를 바꿨다면 `bundle` 또는 `deploy`로 새로 생성합니다. |
| 출력 경로가 거부됨 | 다운로드·배포는 Git 밖에 출력합니다. `export-archive`만 pol2dom의 무시된 `build/archive/`에 출력할 수 있습니다. |
| PDF 교체·컴파일 실패 | PDF 뷰어를 닫고 다시 실행합니다. XeLaTeX 로그의 누락 패키지·이미지·TeX 오류도 확인합니다. |
| PC마다 글꼴이 조금 다름 | Arial/Consolas 설치 여부에 따라 내장 대체 글꼴을 사용합니다. 동일한 toolkit 커밋과 글꼴 환경을 사용합니다. |
| ZIP은 올라갔으나 자동 제출 경고가 나옴 | 업로드 계정의 팀 연결과 대회 설정을 확인하고 실제 채점을 별도로 검증합니다. |
| 전체 연동 후 제출 비활성화 문제가 남음 | 현재 DOMjudge API 문제 목록에 나타나지 않는 항목입니다. 관리 화면에서 별도로 연결을 정리합니다. |

명령의 옵션은 `.venv/Scripts/python -m kgupc_pol2dom <명령> --help`로 확인할 수 있습니다. DOMjudge 9.0.0 서버에서 업로드와 반복 갱신을 확인했으며, 다른 서버 버전에서는 테스트 대회에서 먼저 확인합니다.

## 개발과 라이선스

오프라인 테스트는 다음 명령으로 실행합니다.

```powershell
.venv/Scripts/python -m unittest discover -s tests -v
```

kgupc-pol2dom 자체 코드는 [MIT License](LICENSE)로 배포합니다. 외부 구성요소의 라이선스와 저작권 표기는 각각 유지합니다.

- **kgupc-toolkit**: PDF 템플릿과 글꼴을 제공합니다. 해당 저장소의 라이선스·글꼴 고지를 따릅니다. Beamer 테마에서 유래한 저작권 표기는 toolkit에서 관리합니다.
- **[Polygon2DOMjudge](https://github.com/cn-xcpc-tools/Polygon2DOMjudge)**: `p2d==0.4.0`을 채점용 패키지 변환에 사용합니다. cn-xcpc-tools contributors의 [MIT License](https://github.com/cn-xcpc-tools/Polygon2DOMjudge/blob/master/LICENSE)를 따르며, 포함되는 testlib 등에도 원래의 저작권 표기가 적용됩니다.

참고 문서: [Polygon API](https://codeforces.github.io/polygon-misc/API), [DOMjudge 문제 가져오기](https://www.domjudge.org/docs/manual/9.0/import.html#importing-problems).
