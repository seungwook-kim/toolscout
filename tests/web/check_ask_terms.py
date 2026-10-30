"""질문창 한영 사전 확장 검수. DB 없이 keywords()만 본다.

실행: uv run python -m tests.web.check_ask_terms
"""
import json
import sys
from pathlib import Path

from routes import ask

ROOT = Path(__file__).resolve().parents[2]
failed: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("통과" if ok else "실패"), name)
    if not ok:
        failed.append(name)


table = json.loads((ROOT / "agent" / "term_dict.json").read_text("utf-8"))
check("사전이 비어 있지 않다", len(table) >= 300)
check("한글 표기는 두 글자 이상 한글만", all(f.isalpha() and len(f) >= 2 for fs in table.values() for f in fs))

words = ask.keywords("큐웬 새 모델 100만 토큰 입력 가능해?")
check("큐웬 -> qwen을 원래 낱말 뒤에 덧붙인다", "큐웬" in words and "qwen" in words and words.index("qwen") == words.index("큐웬") + 1)
check("조사가 붙어도 찾는다 (코덱스로)", "codex" in ask.keywords("코덱스로 코드 리뷰 맡기는 방법"))
check("사전에 없는 말은 그대로", ask.keywords("낚시 앱 만들 때 쓸 만한 도구") == ["낚시", "만들", "도구"])
check("영어가 이미 있으면 겹쳐 넣지 않는다", ask.keywords("qwen 큐웬").count("qwen") == 1)
check(f"낱말은 {ask.KEYWORD_MAX}개까지", len(ask.keywords("큐웬 클로드 제미나이 코덱스 노션 슬랙 피그마 도커 깃허브 플레이라이트")) <= ask.KEYWORD_MAX)

check("같은 한글이 영어 둘에 걸리면 둘 다 쓴다 (그록 -> grok, groq)", {"grok", "groq"} <= set(ask.keywords("그록 모델")))

_orig = ask.Path
ask.Path = lambda *a, **k: Path("/없는/경로/term_dict.json")
try:
    check("사전 파일이 없으면 빈 사전으로 동작한다", ask.load_terms() == {})
finally:
    ask.Path = _orig

sys.exit(1 if failed else 0)
