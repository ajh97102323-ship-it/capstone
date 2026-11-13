"""물리 모델 버전 식별 (specs/001 research R5, FR-014).

physics/*.py 소스를 이름순으로 읽어 줄바꿈을 LF로 통일한 뒤 SHA-256을 계산한다. 버전 문자열은
physics/__init__.py를 utf-8-sig로 읽어(BOM 무시) PHYSICS_VERSION을 정규식으로 읽는다(import하지 않으므로
임시 사본에서도 동작). 정의가 정확히 1개가 아니면 ValueError.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# 줄 시작에 고정: 주석(`# ... PHYSICS_VERSION = ...`)이나 접두 이름(`OLD_PHYSICS_VERSION`)은 무시한다.
# 타입 주석(`PHYSICS_VERSION: str = ...`)은 허용한다(T009).
_VERSION_RE = re.compile(r"""^PHYSICS_VERSION\s*(?::\s*str\s*)?=\s*["']([^"']+)["']""", re.MULTILINE)


def _default_root() -> Path:
    """physics 패키지 디렉터리."""
    import physics
    return Path(physics.__file__).resolve().parent


def physics_fingerprint(root: Path | None = None) -> dict:
    """물리 모델 지문 {"version": str, "sha256": str}.

    해시 입력: 파일마다 `이름 + NUL + 내용(CRLF→LF) + NUL`, 파일 이름순.
    하위 디렉터리(`__pycache__` 포함)는 대상이 아니다. 확장자는 정확히 소문자 `.py`만 포함한다
    (Windows의 glob은 대소문자를 구분하지 않으므로 직접 거른다. OS와 무관하게 같은 결과).
    """
    root = Path(root) if root is not None else _default_root()
    files = sorted((f for f in root.glob("*.py") if f.is_file() and f.suffix == ".py"),
                   key=lambda f: f.name)
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode("utf-8") + b"\0")
        h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")

    init = root / "__init__.py"
    if not init.is_file():
        raise ValueError(f"PHYSICS_VERSION을 찾을 수 없음 (파일 없음): {init}")
    # BOM 무시. MULTILINE의 ^는 LF 뒤에서 일치하므로 CRLF 파일도 동작한다.
    text = init.read_bytes().decode("utf-8-sig")
    found = _VERSION_RE.findall(text)
    if len(found) != 1:
        raise ValueError(f"PHYSICS_VERSION 정의가 정확히 1개여야 함 ({len(found)}개): {init}")
    return {"version": found[0], "sha256": h.hexdigest()}
