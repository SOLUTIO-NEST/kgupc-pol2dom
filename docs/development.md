# 개발 및 유지보수

[운영자 안내로 돌아가기](../README.md)

| 프로젝트 | 담당하는 일 |
| --- | --- |
| [kgupc-toolkit](https://github.com/SOLUTIO-NEST/kgupc-toolkit) | 템플릿과 PDF 빌드. 전달받은 지문·해설을 조판합니다. |
| kgupc-pol2dom | Polygon 다운로드, toolkit을 통한 PDF 생성, DOMjudge 연동, 복사용 대회 폴더 내보내기. archive 경로나 접근 권한은 필요하지 않습니다. |
| [kgupc-archive](https://github.com/KGU-SOLUTIO/kgupc-archive) | 종료된 대회의 편집 가능한 `.tex`·이미지·예제·PDF와 템플릿 lock을 보관합니다. 운영자가 내보낸 폴더를 직접 복사하고 공개합니다. |

pol2dom은 archive 저장소를 찾아가거나 그 안의 대회 파일을 갱신하지 않습니다. archive에서 지문·해설을 수정하고 다시 PDF를 만드는 작업은 toolkit을 사용하는 archive의 빌드로 진행합니다.


## 템플릿 고정

대회별 toolkit.lock.json에는 버전과 내용 해시를 기록합니다. 배포한 대회의 toolkit 커밋 또는 wheel을 보관하고, 이전 대회의 템플릿은 변경하지 않습니다.

## 개발과 라이선스

오프라인 테스트는 다음 명령으로 실행합니다.

```powershell
.venv/Scripts/python -m unittest discover -s tests -v
```

kgupc-pol2dom 자체 코드는 [MIT License](../LICENSE)로 배포합니다. 외부 구성요소의 라이선스와 저작권 표기는 각각 유지합니다.

- **kgupc-toolkit**: PDF 템플릿과 글꼴을 제공합니다. 해당 저장소의 라이선스·글꼴 고지를 따릅니다. Beamer 테마에서 유래한 저작권 표기는 toolkit에서 관리합니다.
- **[Polygon2DOMjudge](https://github.com/cn-xcpc-tools/Polygon2DOMjudge)**: `p2d==0.4.0`을 채점용 패키지 변환에 사용합니다. cn-xcpc-tools contributors의 [MIT License](https://github.com/cn-xcpc-tools/Polygon2DOMjudge/blob/master/LICENSE)를 따르며, 포함되는 testlib 등에도 원래의 저작권 표기가 적용됩니다.

참고 문서: [Polygon API](https://codeforces.github.io/polygon-misc/API), [DOMjudge 문제 가져오기](https://www.domjudge.org/docs/manual/9.0/import.html#importing-problems).
