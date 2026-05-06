"""환경 검증 스크립트.

Gemini API + Langfuse 두 서비스에 ping 보내서 연결 OK인지 확인.

실행:
    python3 check_env.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

ok = True

# ----------------------------------------------------
# 1) Gemini API 연결 확인
# ----------------------------------------------------
print("[1/2] Gemini API 연결 확인...")
try:
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_key_here":
        print("  ❌ GEMINI_API_KEY가 .env에 없거나 placeholder입니다.")
        ok = False
    else:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="say hi in one short word",
        )
        text = (response.text or "").strip()
        print(f"  ✅ Gemini OK. 응답 샘플: {text[:30]!r}")
except Exception as e:
    print(f"  ❌ Gemini 연결 실패: {e}")
    ok = False

# ----------------------------------------------------
# 2) Langfuse 연결 확인
# ----------------------------------------------------
print("[2/2] Langfuse 연결 확인...")
try:
    from langfuse import Langfuse

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key or "..." in (public_key + secret_key):
        print("  ❌ Langfuse 키가 .env에 없거나 placeholder입니다.")
        ok = False
    else:
        client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        client.auth_check()
        print(f"  ✅ Langfuse OK. host={host}")
except Exception as e:
    print(f"  ❌ Langfuse 연결 실패: {e}")
    ok = False

# ----------------------------------------------------
print()
if ok:
    print("🎉 모든 연결 정상. 다음 단계: python3 agent.py")
    sys.exit(0)
else:
    print("⚠️  실패한 항목이 있습니다. .env 파일과 키를 다시 확인하세요.")
    sys.exit(1)
