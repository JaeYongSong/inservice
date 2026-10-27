# 휴대폰 사이트 만들기 (_build)

이 폴더는 GitHub Pages에 공개되지 않는다(밑줄로 시작하는 폴더는 Jekyll이 빼고 올림). 비밀은 들어 있지 않다.

## 업데이트 순서 (비밀번호 필요 없음)
1. 클로드 버전(아티팩트 https://claude.ai/artifact/NVjbqj8BgKrboHGf9WUtYW)을 최신으로 고치고 게시한다.
   다른 대화(NR 노트 세션)도 같은 아티팩트를 고치므로, 고치기 전에 항상 최신 게시본을 읽어서 그 위에 고친다.
2. 게시본 페이지를 파일로 받는다(Artifact read → 저장된 HTML). 앞쪽의 호스트 껍데기
   `<!doctype html><html><head>…</head><body>`(첫 줄 끝 `<body>`까지)와 맨 끝 `</body></html>`을 떼어 낸다.
   남는 것은 `<title>인서비스 정리노트</title>`로 시작하는 앱 페이지다.
3. 이 저장소 맨 위 폴더에서 `python3 _build/make_site.py PAGE.html` → `app.bin`과 `index.html`(VER·SIZE)이 바뀐다.
4. `git add index.html app.bin && git commit && git push` (main). 1–2분 뒤 https://jaeyongsong.github.io/inservice/ 에 반영된다.
   폰·맥은 다음에 열 때 새 판을 받는다(기억해 둔 열쇠가 그대로 맞아서 비밀번호를 다시 묻지 않음).

비밀번호를 알면 확인도 할 수 있다(사용자에게 받았을 때만):
- `ISN_PASSWORD='…' python3 _build/make_site.py --check` — app.bin을 풀어 보고 VER가 맞는지 확인
- `ISN_PASSWORD='…' python3 _build/test_site.py` — 브라우저 시험(새 기기, 옛 열쇠를 기억한 기기, 기록 동기화 열쇠 교체, 다른 기기)

## 오류 신고 처리 (매일 자동 작업이 쓰는 순서)
매일 06:47(한국 시간) 클라우드 예약 작업 '인서비스 오류 신고 자동 처리'가 이 순서대로 돈다(맥이 꺼져 있어도 됨).
사이트 열쇠는 그 예약 작업에만 들어 있고, 이 저장소에는 없다.
1. 최신 게시본을 Artifact read → `python3 _build/page.py extract 받은파일 PAGE.html` → `cp PAGE.html PAGE_orig.html`
   → `python3 _build/page.py check PAGE.html`
2. `ISN_KEY='…' python3 _build/read_records.py --page PAGE.html [--json]` — 아직 안 고친 신고, 문항 위치, 그 문항의 형광펜 구역
   (종료 코드 3 = 동기화 파일이 다른 열쇠로 잠겨 있음: 비밀번호를 바꾼 뒤 아직 어느 기기도 새 비밀번호로 열지 않음)
3. 고치기: 고치는 내용을 파이썬 스크립트로 만들어 PAGE.html에 적용한다(게시가 충돌하면 새 판에 그대로 다시 돌릴 수 있게).
   `page.py`의 `Page`로 문항(dict)을 고치고 `resolve({qid: 지금 ms})`, `set_appver(…)`(v50.1 → v50.2 …), `save()`.
   - 문제 문장(stem)은 절대 바꾸지 않는다(문항 ID). 화면에 보이는 문장을 바꿔야 하면 `disp`에 넣는다(앱은 `q.disp||q.stem`을 보여 줌).
     공식 정답(ans가 '공식 정답…')도 바꾸지 않는다. `<en>`은 지우지 않는다.
   - 형광펜 오프셋은 태그·`<en>…</en>` 안쪽·줄바꿈을 뺀 글자 수다. 그래서 칠한 구역 안에서도 해설(exp)의 `\n`(줄바꿈),
     `<b>`/`<i>`, `<en>…</en>`(옅은 글씨로 보임 — 영어 병기, 항목 기호, '점' 같은 짧은 덧말)은 어디든 넣어도 되고,
     보이는 글자를 넣거나 빼는 것은 마지막 칠한 범위 뒤에서만 한다.
   - 화면 코드로 고치는 표시 문제(예: fmtStem은 '가. 나.'와 '가) 나)' 보기를 줄마다 나눈다)는 글자를 바꾸지 말고 `<br>`만 넣는다.
   - 동영상이 없는 문항: 시험 원본 동영상은 공개되지 않았다. 같은 소견의 공개 교육 영상(대학·학회)을 찾으면
     `video`=그 주소, `videoLabel`='▶ 같은 소견 교육 영상 보기 (새 탭)', `videoNote`=무엇을 대신 보여 주는지 + 시험 동영상 소견.
     못 찾으면 `video`를 지우고 `videoNote`만 둔다(점선 상자로 보임). 시험지의 ▶ 아이콘 그림(`img`)은 지운다.
4. 검사: `python3 _build/page.py check PAGE.html` 와
   `ISN_KEY='…' python3 _build/check_edit.py PAGE_orig.html PAGE.html [--show QID …]`
   — 스크립트 오류, 모든 문항 그리기, 사용자의 모든 형광펜이 같은 글자를 가리키는지(동기화 기록 전체)를 본다. `ok`가 나와야 한다.
5. 클로드 버전 게시(같은 URL) → `python3 _build/make_site.py PAGE.html` → `ISN_KEY='…' python3 _build/make_site.py --check` → push.
   공개 저장소라 커밋 메시지·파일에 문제 내용을 쓰지 않는다. 사이트 열쇠(ISN_KEY)는 어디에도 적지 않는다.

## 파일
- `page.py` — 앱 페이지 다루기(호스트 껍데기 떼기, 문항 찾기 = hsh(stem), DATA 고쳐 쓰기, RESOLVED·APPVER).
- `read_records.py` — 동기화 기록(records.enc)을 사이트 열쇠로 열어 오류 신고 목록을 보여 줌.
- `check_edit.py` — 고친 페이지 검사(스크립트 오류, 전체 문항 그리기, 형광펜 글자 보존). Chromium(Playwright) 사용.
- `make_site.py` — 앱 페이지 → app.bin(ISN2)·index.html 상수. 형식 설명은 파일 맨 위.
- `site_key.json` — 사이트 공개키, 비밀번호 열쇠로 잠근 개인키, salt, 반복 횟수(전부 공개해도 됨).
- `set_password.py` — 비밀번호를 바꿀 때만: `ISN_NEW_PASSWORD='…' python3 _build/set_password.py` → make_site → push.
  옛 열쇠를 기억한 기기는 새 비밀번호를 한 번 묻고, 옛 열쇠로 잠긴 동기화 기록(records.enc)은 앱이 한 번 읽어 새 열쇠로 다시 잠근다.
- `test_site.py` — 위 브라우저 시험.

## 열쇠 구조 (2026-10-27~, 앱 v50)
- K = PBKDF2-SHA256(정규화한 비밀번호, salt, 600,000회). 정규화 = NFC·소문자·공백과 하이픈 제거(index.html의 norm과 같음).
- app.bin = "ISN2" | salt(16) | 반복(u32) | wiv(12) | wlen(u16) | 잠근 개인키 | epub(65) | iv(12) | AES-256-GCM(ck, gzip(앱))
  - 잠근 개인키 = AES-256-GCM(K, 사이트 개인키 JWK). 비밀번호를 정할 때 한 번 만들고 그대로 쓴다.
  - 빌드마다 새 P-256 키쌍(epub)으로 ECDH → ck = SHA-256("ISN2" ‖ 공유비밀 ‖ epub). 그래서 빌드에는 공개키만 필요하다.
- 기기는 K를 `isn:unlock`에 기억한다. 공부 기록 동기화 파일(sync 브랜치 records.enc, "ISR1")도 K로 잠근다.
- 예전 "ISN1"(K로 바로 잠근 판)도 index.html이 연다.
