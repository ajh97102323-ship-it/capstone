"""데이터셋 생성 설정 (specs/001 data-model 1·2절, FR-005).

InputSpec: 입력 변수 하나의 이름·단위·범위·스케일. DEFAULT_INPUTS의 순서가 곧 X 배열의 열 순서다.
GenerationConfig: 생성 설정 전체. 경제 변수(비용·가격)는 여기에 두지 않는다(헌법 원칙 IV).
"""
from __future__ import annotations

import dataclasses
import math
import numbers
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from physics import DesignParams

SCALES = ("linear", "log", "int")
_DESIGN_FIELDS = frozenset(f.name for f in dataclasses.fields(DesignParams))

# 물리적 하한 (스케일과 무관하게 적용, 검증 1회차 발견 #8)
_POSITIVE = frozenset({"R", "G_sup", "Pv0", "G_out", "S", "Nbar"})  # lo > 0
_FRACTION = frozenset({"eps", "fill"})                               # 0 < lo < hi <= 1
_MIN_LO = {"N": 1.0, "LD": 0.0}                                      # lo >= 값


def _is_number(x) -> bool:
    """실수형 숫자인지 (bool, 문자열, None 제외. numpy 실수는 허용)."""
    return isinstance(x, numbers.Real) and not isinstance(x, bool)


def _as_int(x, what: str, minimum: int) -> int:
    """정수값(bool 제외, 유한, minimum 이상)인지 확인하고 int로 돌려준다."""
    if not (_is_number(x) and math.isfinite(x) and float(x).is_integer() and x >= minimum):
        raise ValueError(f"{what}는 {minimum} 이상의 정수여야 함: {x!r}")
    return int(x)


def _check_physical(name: str, lo: float, hi: float) -> None:
    if name in _POSITIVE and not lo > 0:
        raise ValueError(f"{name}: 물리적으로 lo > 0 이어야 함 (lo={lo})")
    if name in _FRACTION and not (0 < lo < hi <= 1):
        raise ValueError(f"{name}: 0 < lo < hi <= 1 이어야 함 ({lo}, {hi})")
    if name in _MIN_LO and not lo >= _MIN_LO[name]:
        raise ValueError(f"{name}: lo >= {_MIN_LO[name]:g} 이어야 함 (lo={lo})")


@dataclass(frozen=True)
class InputSpec:
    name: str     # DesignParams 필드 이름
    unit: str     # 단위 표기 (예: "layers", "Pa")
    lo: float     # 하한 [unit]
    hi: float     # 상한 [unit]
    scale: str    # "linear" | "log" | "int"

    def __post_init__(self):
        if self.name not in _DESIGN_FIELDS:
            raise ValueError(f"{self.name!r}: DesignParams 필드가 아님")
        if self.scale not in SCALES:
            raise ValueError(f"{self.name}: 알 수 없는 scale {self.scale!r} (허용: {SCALES})")
        if not (_is_number(self.lo) and _is_number(self.hi)):
            raise ValueError(f"{self.name}: lo, hi는 숫자여야 함 (bool 제외): {self.lo!r}, {self.hi!r}")
        lo, hi = float(self.lo), float(self.hi)
        object.__setattr__(self, "lo", lo)  # 내부 표현은 float로 통일
        object.__setattr__(self, "hi", hi)
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise ValueError(f"{self.name}: 범위는 유한한 수여야 함 ({self.lo}, {self.hi})")
        if not lo < hi:
            raise ValueError(f"{self.name}: lo < hi 이어야 함 ({self.lo} >= {self.hi})")
        if self.scale == "log" and lo <= 0:
            raise ValueError(f"{self.name}: 로그 변수는 lo > 0 이어야 함 (lo={self.lo})")
        if self.scale == "int" and not (lo.is_integer() and hi.is_integer()):
            raise ValueError(f"{self.name}: 정수 변수는 lo, hi가 정수여야 함 ({self.lo}, {self.hi})")
        _check_physical(self.name, lo, hi)

    def to_json_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if self.scale == "int":
            d["lo"], d["hi"] = int(self.lo), int(self.hi)
        return d


# PLAN.md 3.1 / data-model 1절 표와 같다.
DEFAULT_INPUTS: tuple[InputSpec, ...] = (
    InputSpec("N",     "layers",    10,    120,   "int"),
    InputSpec("Nbar",  "layers/cm", 10,    30,    "linear"),
    InputSpec("eps",   "-",         0.02,  0.06,  "linear"),
    InputSpec("G_sup", "W/K",       1e-4,  1e-2,  "log"),
    InputSpec("Pv0",   "Pa",        1e-4,  1e-1,  "log"),
    InputSpec("G_out", "Pa·m³/s",   1e-9,  1e-6,  "log"),
    InputSpec("S",     "m³/s",      1e-4,  1e-2,  "log"),
    InputSpec("R",     "m",         0.3,   2.5,   "linear"),
    InputSpec("LD",    "-",         0,     3,     "linear"),
    InputSpec("fill",  "-",         0.5,   0.95,  "linear"),
)


def _check_unique(inputs: Iterable[InputSpec]) -> None:
    names = [s.name for s in inputs]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f"입력 이름 중복: {dup}")


def _modified_names(inputs: Sequence[InputSpec]) -> list[str]:
    """기본값(DEFAULT_INPUTS)과 범위 또는 스케일이 다른 입력 이름 (inputs 순서)."""
    default = {s.name: s for s in DEFAULT_INPUTS}
    out = []
    for s in inputs:
        d = default.get(s.name)
        if d is None or (float(s.lo), float(s.hi), s.scale) != (float(d.lo), float(d.hi), d.scale):
            out.append(s.name)
    return out


_RANGE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([^:=]+?)\s*:\s*([^:=]+?)\s*$")


def parse_range(s: str, inputs: Sequence[InputSpec] = DEFAULT_INPUTS) -> tuple[str, float, float]:
    """`NAME=LO:HI` → (name, lo, hi). 이름·순서·스케일 규칙을 inputs 기준으로 검증한다."""
    m = _RANGE_RE.match(s) if isinstance(s, str) else None
    if m is None:
        raise ValueError(f"범위 형식 오류 {s!r}: NAME=LO:HI 형식이어야 함")
    name, lo_s, hi_s = m.groups()
    try:
        lo, hi = float(lo_s), float(hi_s)
    except ValueError:
        raise ValueError(f"범위 형식 오류 {s!r}: LO, HI가 숫자가 아님") from None
    spec = {sp.name: sp for sp in inputs}.get(name)
    if spec is None:
        raise ValueError(f"알 수 없는 입력 이름 {name!r} (허용: {[sp.name for sp in inputs]})")
    dataclasses.replace(spec, lo=lo, hi=hi)  # InputSpec 검증 규칙 적용 (실패 시 ValueError)
    return name, lo, hi


def with_ranges(inputs: Sequence[InputSpec], ranges: Iterable[str | tuple]) -> tuple[list[InputSpec], list[str]]:
    """ranges(`"NAME=LO:HI"` 문자열 또는 (name, lo, hi))를 반영한 새 입력 목록과 기본값과 다른 이름 목록.

    defaults_modified는 범위뿐 아니라 스케일이 DEFAULT_INPUTS와 다른 입력도 포함한다(FR-005).
    """
    new = list(inputs)
    _check_unique(new)
    index = {s.name: i for i, s in enumerate(new)}
    for r in ranges or []:
        name, lo, hi = parse_range(r, new) if isinstance(r, str) else r
        if name not in index:
            raise ValueError(f"알 수 없는 입력 이름 {name!r}")
        i = index[name]
        new[i] = dataclasses.replace(new[i], lo=lo, hi=hi)  # 숫자·범위·물리 하한 검증은 InputSpec이 맡음
    return new, _modified_names(new)


# 출력 디렉터리 이름 규칙 (T006 ⑫): 영문자·숫자·_·-·.만, `..` 금지, `.partial`·`.old`로 끝나지 않음
# (끝 이름 검사는 대소문자 무시, T014⑪/T018).
_NAME_RE = re.compile(r"[A-Za-z0-9_.\-]+")
_RESERVED_SUFFIXES = (".partial", ".old")


def _check_name(name) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError(f"name은 비어 있지 않은 문자열이어야 함: {name!r}")
    if _NAME_RE.fullmatch(name) is None:
        raise ValueError(f"name에는 영문자·숫자·'_'·'-'·'.'만 쓸 수 있음: {name!r}")
    if ".." in name or name == ".":
        raise ValueError(f"name에 '..'(또는 '.' 단독)를 쓸 수 없음: {name!r}")
    if name.lower().endswith(_RESERVED_SUFFIXES):  # 대소문자 무시 (Windows, T014⑪)
        raise ValueError(f"name은 {_RESERVED_SUFFIXES}로 끝날 수 없음: {name!r}")


@dataclass(frozen=True)
class GenerationConfig:
    """생성 설정 (data-model 2절). 만든 뒤 바꿀 수 없다(frozen, T006 ⑪).

    physics, created_at, n_valid는 생성 시 `dataclasses.replace`로 채운다.
    """
    name: str | None = None                       # 기본 f"lhs_n{n_requested}_seed{seed}"
    n_requested: int = 10000
    seed: int = 42
    inputs: tuple[InputSpec, ...] = DEFAULT_INPUTS  # 순서가 DEFAULT_INPUTS와 같아야 함 (X 열 순서)
    fixed: dict = field(default_factory=lambda: {"Th": 300.0})  # 고정값 (Th [K])
    days: float = 365.0                           # 시간 격자 끝 [day]
    n_points: int = 100                           # 시간 격자 점 개수 (0일 포함, 등간격)
    split: tuple[float, float, float] = (0.70, 0.15, 0.15)
    physics: dict | None = None                   # {"version", "sha256"} (FR-014)
    created_at: str | None = None                 # ISO 8601
    n_valid: int | None = None
    # 호출자가 넘길 수 없다(init=False). 항상 inputs와 DEFAULT_INPUTS를 비교해 계산한다(T006 ⑦).
    defaults_modified: list[str] = field(init=False, default_factory=list)

    def __post_init__(self):
        def _set(attr, value):  # frozen dataclass에서 검증·정규화한 값을 기록
            object.__setattr__(self, attr, value)

        _set("n_requested", _as_int(self.n_requested, "n_requested", minimum=1))
        _set("seed", _as_int(self.seed, "seed", minimum=0))
        _set("n_points", _as_int(self.n_points, "n_points", minimum=2))
        if self.name is None:
            _set("name", f"lhs_n{self.n_requested}_seed{self.seed}")
        _check_name(self.name)

        try:
            inputs = tuple(self.inputs)
        except TypeError:
            raise ValueError(f"inputs는 InputSpec의 시퀀스여야 함: {self.inputs!r}") from None
        _set("inputs", inputs)
        for s in self.inputs:
            if not isinstance(s, InputSpec):
                raise ValueError(f"inputs 원소는 InputSpec이어야 함: {s!r}")
        _check_unique(self.inputs)
        names = {s.name for s in self.inputs}
        expected = {s.name for s in DEFAULT_INPUTS}
        if len(self.inputs) != len(DEFAULT_INPUTS) or names != expected:
            raise ValueError(f"입력 이름은 {sorted(expected)} 10개와 정확히 같아야 함. "
                             f"빠짐 {sorted(expected - names)}, 남음 {sorted(names - expected)}")
        order = [s.name for s in self.inputs]
        expected_order = [s.name for s in DEFAULT_INPUTS]
        if order != expected_order:  # 순서가 곧 X 배열의 열 순서 (T006 ⑩)
            raise ValueError(f"입력 순서는 {expected_order}와 같아야 함: {order}")

        if not isinstance(self.fixed, dict):
            raise ValueError(f"fixed는 dict여야 함: {self.fixed!r}")
        bad_fixed = sorted(set(self.fixed) - _DESIGN_FIELDS)
        if bad_fixed:
            raise ValueError(f"fixed에 DesignParams 필드가 아닌 이름: {bad_fixed}")
        overlap = sorted(set(self.fixed) & names)
        if overlap:
            raise ValueError(f"fixed와 inputs에 같은 이름: {overlap}")
        for k, v in self.fixed.items():
            if not (_is_number(v) and math.isfinite(v) and v > 0):
                raise ValueError(f"fixed[{k!r}]는 유한한 양수여야 함: {v!r}")
        _set("fixed", dict(self.fixed))  # 호출자 dict와 분리

        if not (_is_number(self.days) and math.isfinite(self.days) and self.days > 0):
            raise ValueError(f"days는 유한한 양수여야 함: {self.days!r}")

        try:
            split = tuple(self.split)
        except TypeError:
            raise ValueError(f"split은 값 3개여야 함: {self.split!r}") from None
        if (len(split) != 3 or not all(_is_number(r) and math.isfinite(r) and r >= 0 for r in split)
                or abs(sum(split) - 1.0) > 1e-9):
            raise ValueError(f"split은 합이 1인 유한한 0 이상의 값 3개여야 함: {self.split!r}")
        _set("split", tuple(float(r) for r in split))
        if self.physics is not None:
            _set("physics", dict(self.physics))

        _set("defaults_modified", _modified_names(self.inputs))

    def to_json_dict(self) -> dict:
        return {
            "name": self.name,
            "n_requested": self.n_requested,
            "n_valid": self.n_valid,
            "seed": self.seed,
            "inputs": [s.to_json_dict() for s in self.inputs],
            "fixed": dict(self.fixed),
            "days": float(self.days),
            "n_points": int(self.n_points),
            "split": list(self.split),
            "physics": None if self.physics is None else dict(self.physics),
            "defaults_modified": _modified_names(self.inputs),  # 항상 현재 inputs로 계산 (T006 ⑪)
            "created_at": self.created_at,
        }
