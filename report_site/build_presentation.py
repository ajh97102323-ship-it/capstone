"""발표 자료 + 브라우저 시연 HTML 한 장을 만든다.

report_site/presentation_template.html 에 학습된 대리모델 데이터(export_demo)와 계산 코어(demo_core.js)를 넣어
docs/presentation.html 을 쓴다. 결과 파일은 서버·인터넷 없이 브라우저로 열기만 하면 슬라이드와 시연이 동작한다.

    python -m report_site.build_presentation [--model models/<이름>] [--out docs/presentation.html]
"""
import argparse
import json
import sys
from pathlib import Path

from optimize import DEFAULT_MODEL
from report_site import export_demo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def render(model_dir) -> str:
    tpl = (HERE / "presentation_template.html").read_text(encoding="utf-8")
    core = (HERE / "demo_core.js").read_text(encoding="utf-8")
    data = json.dumps(export_demo.payload(model_dir), ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    for key in ("__DEMO_DATA__", "/*__DEMO_CORE__*/"):
        if tpl.count(key) != 1:
            raise ValueError(f"템플릿 자리표시 {key}가 정확히 한 번 있어야 함")
    return tpl.replace("__DEMO_DATA__", data).replace("/*__DEMO_CORE__*/", core.replace("</script", "<\\/script"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m report_site.build_presentation", description="발표 자료(시연 포함) HTML 생성")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", default="docs/presentation.html")
    a = ap.parse_args(argv)
    model = Path(a.model)
    if not model.is_absolute() and not model.exists():
        model = ROOT / model
    try:
        html = render(model)
    except (OSError, KeyError, ValueError) as e:
        print(f"ERROR 발표 자료를 만들 수 없음: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
