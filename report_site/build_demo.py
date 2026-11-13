"""시연 전용 페이지(예측·비교·검증·최적화 4개 탭) HTML 한 장을 만든다. Streamlit 앱과 같은 일을 브라우저만으로 한다.

    python -m report_site.build_demo [--model models/<이름>] [--out docs/demo.html]
"""
import argparse
import sys
from pathlib import Path

from optimize import DEFAULT_MODEL
from report_site.build_presentation import ROOT, render


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m report_site.build_demo", description="시연 페이지 HTML 생성")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", default="docs/demo.html")
    a = ap.parse_args(argv)
    model = Path(a.model)
    if not model.is_absolute() and not model.exists():
        model = ROOT / model
    try:
        html = render(model, "demo_template.html")
    except (OSError, KeyError, ValueError) as e:
        print(f"ERROR 시연 페이지를 만들 수 없음: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
