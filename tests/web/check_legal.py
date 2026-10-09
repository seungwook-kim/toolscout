"""공개 법적 안내 글 검수 (2026-10-09): /privacy 개인정보처리방침, /terms 서비스 이용약관.
구글 OAuth 앱을 '프로덕션'으로 게시하려면 홈페이지·방침·약관 링크가 필요하다. 모델 호출 없음, DB 없음.

실행: uv run python -m tests.web.check_legal
- 로그인 없이 200, 색인 허용(noindex 없음, noai는 붙음), robots.txt가 두 주소를 허용, 내용에 시행일·필수 항목
- 첫 화면(/login)·가입 화면(/signup)에는 공통 푸터(web/app.js)가 두 링크를 내므로 app.js에 두 주소가 있는지 본다 (2026-10-09 푸터로 옮김),
  문의 안내는 고객센터 문의(/support)로, 이메일 주소 같은 실제 연락처는 쓰지 않음
"""
import json
import re
import sys

from tests.web import common  # noqa: F401  환경변수를 먼저 채운다


def main() -> int:
    with common.client() as c:
        privacy, terms = c.get("/privacy"), c.get("/terms")
        login, signup = c.get("/login"), c.get("/signup")
        app_js = c.get("/static/app.js").text
        robots = c.get("/robots.txt")
    emails = re.findall(r"[\w.+-]+@[A-Za-z-]+\.[A-Za-z]{2,}", privacy.text + terms.text)
    checks = {
        "방침·약관_로그인없이_200": privacy.status_code == 200 and terms.status_code == 200,
        "색인_허용(noindex_없음)": "noindex" not in privacy.headers.get("x-robots-tag", "") and "noindex" not in terms.headers.get("x-robots-tag", ""),
        "robots.txt가_두_주소_허용": "Allow: /privacy" in robots.text and "Allow: /terms" in robots.text,
        "방침_필수_항목": all(s in privacy.text for s in ("시행일 2026-10-09", "모으는 정보", "맡기는 곳", "보관 기간과 삭제", "이용자의 권리",
                                                       "보이지 않는 표식", "OpenRouter", "Supabase", "Langfuse", "계정 삭제", "기억 지우기")),
        "약관_필수_항목": all(s in terms.text for s in ("시행일 2026-10-09", "AI가 만든 내용", "하면 안 되는 일", "지식재산권", "서비스의 변경과 중단", "책임의 한계")),
        "첫화면·가입화면에_링크(공통_푸터)": all("TS.bare(" in p.text for p in (login, signup)) and 'href="/terms"' in app_js and 'href="/privacy"' in app_js,
        "실제_이메일_주소_없음(문의는_/support)": not emails and 'href="/support"' in privacy.text and "서비스 안 문의 메일" not in privacy.text,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
