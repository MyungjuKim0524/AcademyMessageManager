import argparse
import json
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--java-base-url", required=True)
    parser.add_argument("--python-base-url", required=True)
    args = parser.parse_args()
    fixture = Path(__file__).parents[2] / "tests/fixtures/contract/message-preview-cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
    failed = False
    with httpx.Client(timeout=10) as client:
        for case in cases:
            body = json.dumps(case["body"], ensure_ascii=False).encode()
            headers = {"content-type": case["contentType"]}
            java = client.post(
                f"{args.java_base_url}/api/messages/preview", content=body, headers=headers
            )
            python = client.post(
                f"{args.python_base_url}/api/messages/preview", content=body, headers=headers
            )
            equal = (
                java.status_code == python.status_code == case["expectedStatus"]
                and java.json() == python.json() == case["expectedBody"]
                and java.headers.get("content-type", "").lower()
                == python.headers.get("content-type", "").lower()
            )
            print(f"{case['id']}: {'PASS' if equal else 'FAIL'}")
            if not equal:
                failed = True
                print(f"  java={java.status_code} {java.text}")
                print(f"  python={python.status_code} {python.text}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
