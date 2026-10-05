# kgupc-pol2dom

Polygon에 작성한 문제를 **KGUPC 한글 PDF와 함께 DOMjudge에 업로드**하는 운영자용 프로그램입니다. 아래 순서대로 최초 설정을 마치면, 이후에는 Polygon에서 커밋하고 명령 한 줄로 다시 연동할 수 있습니다.

## 1. 운영자 PC에 설치하기

Python 3.10 이상, Git, [TeX Live](https://tug.org/texlive/)가 필요합니다. TeX 설치에는 XeLaTeX, latexmk, kotex가 포함되어야 합니다. 설치 후 새 PowerShell에서 `python --version`, `git --version`, `xelatex --version`, `latexmk -v`가 실행되는지 확인합니다.

아래 명령을 순서대로 실행합니다. 이미 내려받은 저장소가 있다면 그 폴더로 이동하고 `python -m venv .venv`부터 실행합니다.

```powershell
git clone https://github.com/SOLUTIO-NEST/kgupc-pol2dom.git
cd kgupc-pol2dom
python -m venv .venv
.venv/Scripts/python -m pip install "kgupc-toolkit @ git+https://github.com/SOLUTIO-NEST/kgupc-toolkit.git@373249973347711ef7aaed1283aa328ae3c23b66"
.venv/Scripts/python -m pip install .
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

이 문서의 모든 명령은 **kgupc-pol2dom 폴더 안의 PowerShell**에서 실행합니다. `.venv`를 별도로 활성화할 필요는 없습니다. 프로그램을 업데이트했다면 `.venv/Scripts/python -m pip install .`을 다시 실행합니다. Linux/macOS에서는 `.venv/Scripts/python` 대신 `.venv/bin/python`을 사용합니다.

## 2. 서버 담당자에게 준비를 요청하기

DOMjudge에 대상 대회와 실제 채점을 수행할 **judgehost**가 있어야 합니다. 이 프로그램은 기존 대회에 문제를 올리며, 대회나 judgehost를 설치하지 않습니다.

업로드와 채점은 다음처럼 진행됩니다.

1. pol2dom이 지문 PDF·테스트·채점기·정답 코드를 업로드합니다.
2. DOMjudge가 패키지의 정답 코드와 오답 검증 코드를 시험 제출합니다.
3. judgehost가 코드를 컴파일하고 테스트를 실행합니다. 출력은 문제의 채점기로 비교합니다.
4. 운영자가 예상 판정과 실제 판정이 일치하는지 확인합니다.

**admin 역할은 문제를 업로드할 권한이고, 팀 연결은 시험 제출의 소유자를 지정하는 설정입니다.** admin 권한만 있어도 문제는 올라가지만, 팀이 연결되지 않으면 정답 코드 자동 제출이 생략될 수 있습니다.

서버 담당자에게 다음 설정을 요청하거나, admin 관리 화면에서 직접 설정합니다.

1. **Teams**에서 `jury-test` 같은 운영진 검증용 팀을 만듭니다. 실제 참가팀과 구분할 수 있도록 비공개 또는 점수판 제외 설정을 확인합니다.
2. **Contests**에서 대상 대회의 참가 팀에 이 검증용 팀을 포함합니다.
3. **Users**에서 `.env`에 넣을 업로드 계정을 편집합니다. **admin 역할을 유지하고 Team 항목에 검증용 팀을 연결**합니다. 계정 이름이 꼭 `admin`일 필요는 없습니다.
4. 대상 대회의 **Activate time**을 현재보다 이전으로 설정합니다. 대회 시작 시각을 앞당길 필요는 없습니다. 문제의 **Allow submit / Allow judge**도 활성화되어 있어야 합니다.
5. **Judgehosts**에서 채점 서버가 활성 상태인지 확인하고 **Config checker**로 서버 설정을 점검합니다.

검증용 팀과 계정 설정은 서버에서 한 번 준비하면 됩니다. pol2dom이 운영진 계정의 권한이나 참가팀·대회 일정을 자동으로 변경하지 않습니다. 자세한 조건은 [DOMjudge 공식 안내](https://www.domjudge.org/docs/manual/9.0/config-basic.html#testing-jury-solutions)를 참고합니다.

## 3. `.env` 채우기

`.env.example`을 복사한 `.env`에 실제 값을 입력합니다. 아래는 예시입니다.

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
DOMJUDGE_CONTEST_ID=your_contest_external_id
```

| 설정 | 입력할 내용 |
| --- | --- |
| `POLYGON_API_KEY`, `POLYGON_API_SECRET` | Polygon Settings에서 발급한 키와 시크릿. 해당 대회·문제 접근 권한이 있는 계정을 사용합니다. |
| `POLYGON_CONTEST_URL` | 가져올 Polygon 대회 링크. |
| `CONTEST_SLUG` | 로컬 복사용 폴더 이름. `2025`, `2026-spring`, `2026-fall` 등. |
| `CONTEST_TITLE` | PDF에 표시할 대회명. |
| `CONTEST_DATE` | PDF에 표시할 날짜. `YYYY-MM-DD`; 비우면 표시하지 않습니다. |
| `CONTEST_AUTHOR` | PDF에 표시할 주최자 이름. |
| `DOMJUDGE_URL` | 서버 주소. `/domjudge` 같은 설치 경로가 있으면 포함합니다. |
| `DOMJUDGE_USERNAME`, `DOMJUDGE_PASSWORD` | 앞서 설정한 admin 역할 계정의 이름과 비밀번호. 별도 DOMjudge API 키는 필요하지 않습니다. |
| `DOMJUDGE_CONTEST_ID` | 다음 명령에서 조회한 대상 대회의 `id`. |

```powershell
.venv/Scripts/python -m kgupc_pol2dom domjudge-list
```

조회 결과의 `contests[].id`를 사용합니다. 관리 화면의 **External ID**에 해당하며, 내부 숫자 Contest ID나 표시 이름으로 추측하지 않습니다. 연동을 시작한 뒤 External ID는 유지하고, 표시 이름은 Shortname / Name에서 변경합니다.

Polygon에서 API PIN을 요구하면 `POLYGON_PIN`도 입력합니다. 공유 링크의 `ccid`와는 다릅니다. 공백이나 `#`가 포함된 값은 따옴표로 감쌉니다. 제목·작성자에는 TeX 명령 대신 일반 텍스트를 입력합니다.

`.env`와 생성된 `build/`는 Git에서 제외됩니다. `.env` 수정은 다음 생성 때 적용되며, 이미 업로드된 PDF는 연동 명령을 다시 실행해야 바뀝니다.

## 4. Polygon에서 문제 준비하기

한글 지문은 `korean` 언어로 작성합니다. 예제·테스트·채점기·정답 코드·시간 및 메모리 제한을 확인한 뒤 **수정 사항을 커밋**합니다. 배포는 커밋된 문제를 사용합니다.

Java 검증 코드는 **`Main` 클래스에 `public static void main(String[] args)`를 두고 package 선언 없이** 작성합니다. 프로그램은 Java 파일을 각각 별도 폴더의 `Main.java`로 패키징합니다. 여러 Java 정답이 있어도 서로 덮어쓰지 않으며, 클래스 이름이나 코드 내용은 자동 변경하지 않습니다. 서버에 Java 언어와 컴파일러도 설치되어 있어야 합니다.

가져올 대회와 문제 목록을 확인합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom polygon-list
```

현재는 **표준 입출력을 사용하는 일반 문제**를 지원합니다. 인터랙티브·멀티패스·파일 입출력 문제는 지원하지 않습니다.

## 5. 문제 업로드하기

설정이 끝나면 다음 한 줄을 실행합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom deploy --build-packages
```

Polygon 다운로드 → 통합·개별 한글 PDF 생성 → 로컬 복사용 폴더 생성 → DOMjudge 업로드 순서로 진행합니다. `--build-packages`는 현재 커밋의 Linux Full 패키지가 없으면 Polygon에 검증·빌드를 요청하므로 문제 쓰기 권한이 필요합니다. 빌드에 시간이 걸릴 수 있습니다.

**전체 연동은 `.env`로 지정한 DOMjudge 대회의 문제 목록을 Polygon에 맞춥니다.** 기존 문제는 갱신하고, 새 문제는 추가하며, Polygon에 없는 문제는 해당 대회에서 연결을 해제합니다. 다른 대회의 연결이나 전역 문제를 삭제하지 않습니다.

PDF를 먼저 검토하고 싶으면 아래 명령으로 생성만 합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom bundle --build-packages
```

`build/archive/<CONTEST_SLUG>/problems/main.pdf`와 각 문제 폴더의 PDF를 검토한 뒤, 출력된 **실제 실행 폴더 경로**로 업로드합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom upload "C:/Users/me/kgupc-work/deploy-12345/runs/실행-ID"
```

## 6. 실제 채점까지 확인하기

**업로드 완료는 채점 정상 동작까지 확인했다는 뜻이 아닙니다.** DOMjudge 관리 화면에서 다음을 확인합니다.

1. **Problems**: 문제 번호·이름·제한·테스트 수와 내려받은 PDF가 맞는지 확인합니다.
2. **Submissions**: 업로드한 정답 코드의 시험 제출이 생겼는지 확인합니다.
3. **Judging Verifier**: 실제 판정이 예상 판정과 일치하는지 확인합니다. 정답 코드는 Accepted, 의도한 오답·시간 초과 코드는 해당 예상 판정이어야 합니다.

| 증상 | 조치 |
| --- | --- |
| 팀 연결이 필요하다는 경고 / 시험 제출이 없음 | 2번 단계의 업로드 계정 Team 연결·대회 참가 설정·활성 상태를 확인하고 다시 업로드합니다. |
| 제출은 있지만 Pending으로 남음 | Judgehosts 활성 상태와 문제 Allow judge, 서버 채점 로그를 확인합니다. |
| Java Compile Error | `Main` 클래스와 main 메서드, package 선언 여부, Java 컴파일러 설정을 확인합니다. Submissions의 컴파일 로그에서 원인을 확인합니다. |
| 정답 코드가 Wrong Answer / Runtime Error / Time Limit Exceeded | 입력·정답 데이터, 채점기, 제한과 정답 코드 실행 결과를 확인합니다. 파일이 올라갔다는 이유로 정상 판정이라고 간주하지 않습니다. |
| 401 / 403 | 계정 정보와 admin 역할, 대회 잠금 여부를 확인합니다. |
| Polygon 패키지 빌드 실패 | Polygon Packages에서 검증 로그를 확인하고 문제를 수정·커밋합니다. |
| 도구나 PDF 컴파일 오류 | Python·XeLaTeX·latexmk 설치와 PATH를 확인합니다. PDF가 잠겼다면 뷰어를 닫고 다시 실행합니다. |

팀 설정을 고친 뒤에는 처음과 같은 `deploy --build-packages` 또는 이미 생성한 실행 폴더의 `upload`를 사용하면 됩니다. 재업로드하면 시험 제출이 다시 생성될 수 있습니다. 자동 제출과 실제 채점에 관한 기준은 [DOMjudge 문제 패키지 안내](https://www.domjudge.org/docs/manual/9.0/problem-format.html)에서 확인할 수 있습니다.

## 7. 수정본 다시 반영하기

Polygon에서 수정하고 커밋한 뒤 같은 명령을 실행합니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom deploy --build-packages
```

특정 문제만 반영할 수도 있습니다. 이 경우 다른 문제와 전체 복사용 폴더는 유지됩니다.

```powershell
.venv/Scripts/python -m kgupc_pol2dom deploy --letters A B --build-packages
```

업로드 도중 실패했다면 일부만 반영되었을 수 있습니다. 오류를 해결하고 같은 실행 폴더로 `upload`를 다시 실행한 뒤 서버의 전체 문제 목록을 확인합니다.

## 8. 대회 종료 후 보관하기

전체 실행마다 `build/archive/<CONTEST_SLUG>/`에 편집 가능한 `.tex`·이미지·예제·통합/개별 PDF가 생성됩니다. 이전 출력은 `build/archive/history/`에 백업됩니다.

대회 종료 후 실제 최종 업로드본인지 확인하고 **`<CONTEST_SLUG>` 폴더 자체를 kgupc-archive 루트에 복사**합니다. 공개 여부를 검토한 뒤 archive에서 commit/push합니다. pol2dom은 archive 저장소에 접근하거나 자동으로 공개하지 않습니다. 부분 연동만 했다면 최종 전체 결과물도 생성해 검토합니다.

**공개 전 문제 유출 방지를 위한 정책:** `build/` 전체는 `.gitignore`로 Git에서 제외됩니다. 생성된 자료는 운영자 로컬에만 보관되며, pol2dom이 kgupc-archive에 자동으로 접근하거나 자료를 저장·commit·push하지 않습니다. 대회 종료 후 운영자가 공개 여부와 최종본을 확인하고 직접 복사하는 절차는, 준비 중인 대회의 문제가 공개 저장소에 유출되는 최악의 상황을 막기 위해 의도적으로 마련한 과정입니다. **앞으로도 이 절차를 생략하거나 archive 자동 접근·저장·공개 기능을 추가하지 마세요.**

명령·출력 경로·과거 결과물 내보내기는 [상세 참고](docs/reference.md), 프로그램 개발·템플릿 버전·라이선스는 [개발 문서](docs/development.md)를 참고합니다.
