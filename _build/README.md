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
1. 최신 게시본을 Artifact read → `python3 _build/page.py extract 받은파일 PAGE.html` → `python3 _build/page.py check PAGE.html`
2. `ISN_KEY='…' python3 _build/read_records.py --page PAGE.html` — 아직 안 고친 신고, 문항 위치, 그 문항의 형광펜 구역
   (종료 코드 3 = 동기화 파일이 다른 열쇠로 잠겨 있음: 비밀번호를 바꾼 뒤 아직 어느 기기도 새 비밀번호로 열지 않음)
3. 고치기: `page.py`의 `Page`로 문항(dict)을 고치고 `resolve({qid: 지금 ms})`, `set_appver(…)`, `save()`.
   문제 문장(stem)은 절대 바꾸지 않는다(문항 ID). `<en>`은 지우지 않는다. 형광펜 구역은 칠한 부분 뒤에만 덧붙인다.
4. 클로드 버전 게시(같은 URL) → `python3 _build/make_site.py PAGE.html` → `ISN_KEY='…' python3 _build/make_site.py --check` → push.
   공개 저장소라 커밋 메시지·파일에 문제 내용을 쓰지 않는다. 사이트 열쇠(ISN_KEY)는 어디에도 적지 않는다.

## 파일
- `page.py` — 앱 페이지 다루기(호스트 껍데기 떼기, 문항 찾기 = hsh(stem), DATA 고쳐 쓰기, RESOLVED·APPVER).
- `read_records.py` — 동기화 기록(records.enc)을 사이트 열쇠로 열어 오류 신고 목록을 보여 줌.
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
