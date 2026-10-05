# 명령 및 결과물 상세 참고

[운영자 안내로 돌아가기](../README.md)

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

