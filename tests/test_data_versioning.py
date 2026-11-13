"""물리 모델 버전 식별 테스트 (specs/001 T005): physics_fingerprint의 해시 안정성과 변경 감지."""
import re
import shutil
from pathlib import Path

import pytest

import physics
from data.versioning import physics_fingerprint

PHYSICS_DIR = Path(physics.__file__).resolve().parent


@pytest.fixture
def physics_copy(tmp_path):
    """physics/*.py만 tmp_path/physics로 복사한 사본 디렉터리."""
    dst = tmp_path / "physics"
    dst.mkdir()
    for f in PHYSICS_DIR.glob("*.py"):
        shutil.copyfile(f, dst / f.name)
    return dst


def test_same_content_same_hash(physics_copy):
    a = physics_fingerprint(root=physics_copy)
    b = physics_fingerprint(root=physics_copy)
    original = physics_fingerprint(root=PHYSICS_DIR)
    assert a["sha256"] == b["sha256"] == original["sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", a["sha256"])


@pytest.mark.parametrize("to_crlf", [True, False])
def test_line_endings_do_not_change_hash(physics_copy, to_crlf):
    before = physics_fingerprint(root=physics_copy)["sha256"]
    changed = 0
    for f in physics_copy.glob("*.py"):
        raw = f.read_bytes()
        lf = raw.replace(b"\r\n", b"\n")
        new = lf.replace(b"\n", b"\r\n") if to_crlf else lf
        if b"\n" in lf:
            changed += 1
        f.write_bytes(new)
    assert changed > 0  # 실제로 줄바꿈이 있는 파일을 바꿨는지
    assert physics_fingerprint(root=physics_copy)["sha256"] == before


def test_added_comment_changes_hash(physics_copy):
    before = physics_fingerprint(root=physics_copy)["sha256"]
    target = physics_copy / "model.py"
    target.write_bytes(target.read_bytes() + b"# comment\n")
    assert physics_fingerprint(root=physics_copy)["sha256"] != before


def test_added_py_file_changes_hash(physics_copy):
    before = physics_fingerprint(root=physics_copy)["sha256"]
    (physics_copy / "extra.py").write_bytes(b"")
    assert physics_fingerprint(root=physics_copy)["sha256"] != before


def test_pycache_ignored(physics_copy):
    before = physics_fingerprint(root=physics_copy)["sha256"]
    cache = physics_copy / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_bytes(b"\x00garbage")
    assert physics_fingerprint(root=physics_copy)["sha256"] == before


def test_version_matches_physics_version(physics_copy):
    assert physics_fingerprint(root=physics_copy)["version"] == physics.PHYSICS_VERSION
    assert physics_fingerprint()["version"] == physics.PHYSICS_VERSION


def test_renamed_file_changes_hash(physics_copy):
    before = physics_fingerprint(root=physics_copy)["sha256"]
    (physics_copy / "heat.py").rename(physics_copy / "heat_renamed.py")
    assert physics_fingerprint(root=physics_copy)["sha256"] != before


def test_subdirectory_py_ignored(physics_copy):
    before = physics_fingerprint(root=physics_copy)["sha256"]
    sub = physics_copy / "sub"
    sub.mkdir()
    (sub / "extra.py").write_bytes(b"X = 1\n")
    assert physics_fingerprint(root=physics_copy)["sha256"] == before


def _set_init(physics_copy, transform):
    init = physics_copy / "__init__.py"
    text = init.read_bytes().decode("utf-8")
    assert re.search(r'^PHYSICS_VERSION\s*=', text, re.M)  # 전제: 실제 정의가 있음
    init.write_bytes(transform(text).encode("utf-8"))


def test_version_read_from_file_not_import(physics_copy):
    _set_init(physics_copy, lambda s: re.sub(r'(^PHYSICS_VERSION\s*=\s*)["\'][^"\']+["\']',
                                             r'\g<1>"9.9.9"', s, count=1, flags=re.M))
    assert physics_fingerprint(root=physics_copy)["version"] == "9.9.9"
    assert physics.PHYSICS_VERSION != "9.9.9"


def test_version_ignores_comment_and_prefixed_name(physics_copy):
    decoys = '# old: PHYSICS_VERSION = "0.0.1"\nOLD_PHYSICS_VERSION = "0.0.2"\n'
    _set_init(physics_copy, lambda s: decoys + s)
    assert physics_fingerprint(root=physics_copy)["version"] == physics.PHYSICS_VERSION


def test_uppercase_extension_excluded(physics_copy):
    before = physics_fingerprint(root=physics_copy)["sha256"]
    (physics_copy / "Upper.PY").write_bytes(b"X = 1\n")
    assert physics_fingerprint(root=physics_copy)["sha256"] == before


def test_version_ignores_utf8_bom(physics_copy):
    """⑫ __init__.py 앞에 UTF-8 BOM이 있어도 버전을 읽는다(검증 2회차 발견 #2)."""
    init = physics_copy / "__init__.py"
    init.write_bytes(b"\xef\xbb\xbf" + init.read_bytes())
    assert init.read_bytes().startswith(b"\xef\xbb\xbfPHYSICS_VERSION")  # 전제: BOM 바로 뒤가 정의
    assert physics_fingerprint(root=physics_copy)["version"] == "0.1.0"


def test_version_allows_type_annotation(physics_copy):
    """⑬ `PHYSICS_VERSION: str = "0.1.0"` 형태도 읽는다."""
    _set_init(physics_copy, lambda s: re.sub(r'^PHYSICS_VERSION\s*=', 'PHYSICS_VERSION: str =',
                                             s, count=1, flags=re.M))
    assert 'PHYSICS_VERSION: str = "0.1.0"' in (physics_copy / "__init__.py").read_text("utf-8")
    assert physics_fingerprint(root=physics_copy)["version"] == "0.1.0"


@pytest.mark.parametrize("second", [
    'PHYSICS_VERSION = "0.2.0"\n',
    'PHYSICS_VERSION: str = "0.2.0"\n',
    'PHYSICS_VERSION = "0.1.0"\n',      # 같은 값이어도 정의가 둘이면 거부
])
def test_duplicate_version_definition_raises(physics_copy, second):
    """⑭ 정의가 두 번이면 ValueError(import 결과와 정규식 결과가 달라지는 것을 막음, 발견 #3)."""
    _set_init(physics_copy, lambda s: s + "\n" + second)
    with pytest.raises(ValueError):
        physics_fingerprint(root=physics_copy)
