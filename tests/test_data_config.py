"""입력 설정 테스트 (specs/001 T006): DEFAULT_INPUTS, parse_range, with_ranges, 스케일 변경(FR-005)."""
import dataclasses

import numpy as np
import pytest

from data.config import DEFAULT_INPUTS, GenerationConfig, InputSpec, parse_range, with_ranges
from physics import DesignParams

EXPECTED_NAMES = ["N", "Nbar", "eps", "G_sup", "Pv0", "G_out", "S", "R", "LD", "fill"]


def test_default_inputs_order_and_fields():
    names = [s.name for s in DEFAULT_INPUTS]
    assert names == EXPECTED_NAMES
    fields = {f.name for f in dataclasses.fields(DesignParams)}
    assert set(names) <= fields


def test_parse_range_valid():
    assert parse_range("R=0.5:2.5") == ("R", 0.5, 2.5)


@pytest.mark.parametrize("s", [
    "X=1:2",        # 알 수 없는 이름
    "R=2:1",        # lo >= hi
    "Pv0=0:1",      # 로그 변수 lo <= 0
    "N=10.5:120",   # 정수 변수에 정수 아닌 값
    "R0.5:2.5",     # 형식 오류
])
def test_parse_range_invalid(s):
    with pytest.raises(ValueError):
        parse_range(s)


def test_with_ranges_reports_modified():
    new_inputs, modified = with_ranges(DEFAULT_INPUTS, ["R=0.5:2.5", "fill=0.6:0.9"])
    assert modified == ["R", "fill"]
    by_name = {s.name: s for s in new_inputs}
    assert (by_name["R"].lo, by_name["R"].hi) == (0.5, 2.5)
    assert (by_name["fill"].lo, by_name["fill"].hi) == (0.6, 0.9)
    assert [s.name for s in new_inputs] == EXPECTED_NAMES
    # 바꾸지 않은 입력은 기본값 그대로
    for old, new in zip(DEFAULT_INPUTS, new_inputs):
        if old.name not in modified:
            assert old == new
    # 원본은 바뀌지 않는다
    assert {s.name: (s.lo, s.hi) for s in DEFAULT_INPUTS}["R"] == (0.3, 2.5)

    _, none_modified = with_ranges(DEFAULT_INPUTS, [])
    assert none_modified == []


def _linear_gsup_inputs():
    return [dataclasses.replace(s, scale="linear") if s.name == "G_sup" else s
            for s in DEFAULT_INPUTS]


def test_scale_change_recorded_in_config():
    inputs = _linear_gsup_inputs()
    cfg = GenerationConfig(inputs=inputs)
    d = cfg.to_json_dict()
    rec = {i["name"]: i for i in d["inputs"]}
    assert rec["G_sup"]["scale"] == "linear"
    assert rec["Pv0"]["scale"] == "log"
    assert "G_sup" in d["defaults_modified"]
    assert "G_sup" in cfg.defaults_modified
    _, modified = with_ranges(inputs, [])
    assert "G_sup" in modified


def test_generation_config_defaults():
    cfg = GenerationConfig()
    assert cfg.n_requested == 10000
    assert cfg.seed == 42
    assert cfg.fixed == {"Th": 300.0}
    assert cfg.days == 365.0
    assert cfg.n_points == 100
    assert tuple(cfg.split) == (0.70, 0.15, 0.15)
    assert cfg.name == "lhs_n10000_seed42"
    assert GenerationConfig(n_requested=300, seed=1).name == "lhs_n300_seed1"
    assert cfg.defaults_modified == []


# ---------------------------------------------------------------- ⑥ 입력 10개 정확히

def _spec(name):
    return {s.name: s for s in DEFAULT_INPUTS}[name]


@pytest.mark.parametrize("inputs", [
    [s for s in DEFAULT_INPUTS if s.name != "fill"],                       # 빠짐
    list(DEFAULT_INPUTS)[:9],                                               # 빠짐
    list(DEFAULT_INPUTS) + [InputSpec("Th", "K", 250.0, 320.0, "linear")],  # 남음
    list(DEFAULT_INPUTS) + [_spec("R")],                                    # 중복
    [s for s in DEFAULT_INPUTS if s.name != "fill"] + [_spec("R")],         # 개수는 10이지만 중복·빠짐
    [],
])
def test_config_requires_exact_default_input_names(inputs):
    with pytest.raises(ValueError):
        GenerationConfig(inputs=inputs, fixed={})


# ---------------------------------------------------------------- ⑦ defaults_modified는 항상 계산

def test_defaults_modified_always_computed():
    try:
        cfg = GenerationConfig(defaults_modified=["R", "bogus"])
    except TypeError:
        cfg = None
    if cfg is not None:  # 받는다면 무시되어야 한다
        assert cfg.defaults_modified == []
        assert cfg.to_json_dict()["defaults_modified"] == []

    new_inputs, _ = with_ranges(DEFAULT_INPUTS, ["R=0.5:2.5"])
    try:
        cfg2 = GenerationConfig(inputs=new_inputs, defaults_modified=[])
    except TypeError:
        cfg2 = GenerationConfig(inputs=new_inputs)
    assert cfg2.defaults_modified == ["R"]
    assert cfg2.to_json_dict()["defaults_modified"] == ["R"]


# ---------------------------------------------------------------- ⑧ 숫자 검증

NAN, INF = float("nan"), float("inf")


@pytest.mark.parametrize("kwargs", [
    dict(split=(NAN, 0.15, 0.15)),
    dict(split=(0.7, NAN, 0.15)),
    dict(split=(0.7, 0.2, 0.2)),          # 합 ≠ 1
    dict(split=(0.5, 0.25, 0.2)),         # 합 ≠ 1
    dict(days=NAN), dict(days=INF), dict(days=0.0), dict(days=-1.0), dict(days="365"),
    dict(n_requested=0), dict(n_requested=-5), dict(n_requested=NAN), dict(n_requested=INF),
    dict(n_requested=10.5), dict(n_requested="100"), dict(n_requested=True),
    dict(fixed={"Th": NAN}), dict(fixed={"Th": INF}), dict(fixed={"Th": 0.0}),
    dict(fixed={"Th": -300.0}), dict(fixed={"Th": "300"}), dict(fixed={"Th": True}),
])
def test_config_numeric_validation(kwargs):
    with pytest.raises(ValueError):
        GenerationConfig(**kwargs)


@pytest.mark.parametrize("lo, hi", [
    ("0.3", 2.5), (0.3, "2.5"), (True, 2.5), (0.3, None), (None, 2.5), (NAN, 2.5), (0.3, INF),
])
def test_inputspec_requires_numbers(lo, hi):
    with pytest.raises(ValueError):
        InputSpec("R", "m", lo, hi, "linear")


def test_inputspec_accepts_numpy_numbers():
    s = InputSpec("R", "m", np.float64(0.5), np.float64(2.0), "linear")
    assert (s.lo, s.hi) == (0.5, 2.0)


# ---------------------------------------------------------------- ⑨ 물리적 하한

BAD_PHYSICAL = [
    "R=0:2.5", "R=-1:2.5",
    "Nbar=0:30", "Nbar=-5:30",
    "N=0:120", "N=-10:120",
    "LD=-0.5:3",
    "eps=0:0.06", "eps=-0.01:0.06", "eps=0.02:1.5",
    "fill=0:0.9", "fill=0.5:1.01",
]


@pytest.mark.parametrize("s", BAD_PHYSICAL)
def test_parse_range_physical_bounds(s):
    with pytest.raises(ValueError):
        parse_range(s)


@pytest.mark.parametrize("s", BAD_PHYSICAL)
def test_with_ranges_physical_bounds(s):
    with pytest.raises(ValueError):
        with_ranges(DEFAULT_INPUTS, [s])
    name, lo, hi = s.split("=")[0], *map(float, s.split("=")[1].split(":"))
    with pytest.raises(ValueError):
        with_ranges(DEFAULT_INPUTS, [(name, lo, hi)])


@pytest.mark.parametrize("name", ["G_sup", "Pv0", "G_out", "S"])
def test_positive_bound_holds_even_with_linear_scale(name):
    """로그 스케일 조건과 별개로 물리적 하한 lo > 0을 지킨다(스케일을 linear로 바꿔도)."""
    inputs = [dataclasses.replace(s, scale="linear") if s.name == name else s for s in DEFAULT_INPUTS]
    hi = _spec(name).hi
    with pytest.raises(ValueError):
        with_ranges(inputs, [f"{name}=0:{hi}"])
    with pytest.raises(ValueError):
        with_ranges(inputs, [(name, -1.0, hi)])
    with pytest.raises(ValueError):
        parse_range(f"{name}=0:{hi}", inputs)


@pytest.mark.parametrize("s", ["N=1:120", "LD=0:3", "eps=0.02:1", "fill=0.5:1", "R=0.01:2.5"])
def test_physical_bounds_allow_edges(s):
    name = s.split("=")[0]
    assert parse_range(s)[0] == name
    _, modified = with_ranges(DEFAULT_INPUTS, [s])
    assert modified in ([], [name])


# ---------------------------------------------------------------- ⑩ 입력 순서 강제

@pytest.mark.parametrize("perm", [
    lambda xs: list(reversed(xs)),
    lambda xs: [xs[1], xs[0]] + xs[2:],         # 앞 두 개만 바꿈
    lambda xs: xs[:-2] + [xs[-1], xs[-2]],      # 뒤 두 개만 바꿈
])
def test_config_requires_default_input_order(perm):
    inputs = perm(list(DEFAULT_INPUTS))
    assert {s.name for s in inputs} == set(EXPECTED_NAMES)  # 전제: 이름 집합은 같음
    with pytest.raises(ValueError):
        GenerationConfig(inputs=inputs)


# ---------------------------------------------------------------- ⑪ frozen

def test_inputspec_is_frozen():
    s = DEFAULT_INPUTS[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.lo = 1.0


@pytest.mark.parametrize("field_name, value", [
    ("inputs", []), ("name", "x"), ("n_requested", 5), ("seed", 3), ("days", 10.0),
    ("split", (0.8, 0.1, 0.1)), ("defaults_modified", ["R"]),
])
def test_generation_config_is_frozen(field_name, value):
    cfg = GenerationConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(cfg, field_name, value)


def test_generation_config_inputs_is_tuple_and_isolated():
    src = list(DEFAULT_INPUTS)
    cfg = GenerationConfig(inputs=src)
    assert isinstance(cfg.inputs, tuple)
    assert [s.name for s in cfg.inputs] == EXPECTED_NAMES
    # 호출자 리스트를 나중에 바꿔도 cfg는 영향을 받지 않는다
    src[7] = dataclasses.replace(src[7], lo=0.5)
    assert cfg.inputs[7].lo == 0.3
    assert cfg.to_json_dict()["defaults_modified"] == []
    with pytest.raises((TypeError, AttributeError)):
        cfg.inputs[0] = src[0]  # tuple은 원소 대입 불가


def test_to_json_defaults_modified_reflects_current_inputs():
    new_inputs, _ = with_ranges(DEFAULT_INPUTS, ["R=0.5:2.5"])
    cfg = GenerationConfig(inputs=new_inputs)
    assert cfg.to_json_dict()["defaults_modified"] == ["R"]
    cfg2 = dataclasses.replace(cfg, inputs=DEFAULT_INPUTS)
    assert cfg2.to_json_dict()["defaults_modified"] == []
    assert cfg2.defaults_modified == []


# ---------------------------------------------------------------- ⑫ name 형식

@pytest.mark.parametrize("name", [
    "", "a/b", "a\\b", "..", ".", "a..b", "../x", "x.partial", "x.old",
    "한글", "a b", "a:b", "a*b", "a\nb", 123,
])
def test_config_name_validation_rejects(name):
    with pytest.raises(ValueError):
        GenerationConfig(name=name)


@pytest.mark.parametrize("name", ["lhs_n300_seed1", "repro-a", "v1.2", "A_b-c.d", "x.partial2", "old"])
def test_config_name_validation_accepts(name):
    assert GenerationConfig(name=name).name == name
