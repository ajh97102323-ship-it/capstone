"""70/15/15 분할 테스트 (specs/001 T013): split_labels(n, ratios, rng) -> int8[n]."""
import numpy as np
import pytest

from data.split import split_labels

RATIOS = (0.70, 0.15, 0.15)


@pytest.mark.parametrize("n, expected", [
    (10000, (7000, 1500, 1500)),
    (999, (699, 150, 150)),      # round(0.7·999)=699, round(0.15·999)=150, 나머지 150
    (300, (210, 45, 45)),
])
def test_counts(n, expected):
    lab = split_labels(n, RATIOS, np.random.default_rng(0))
    assert lab.dtype == np.int8
    assert lab.shape == (n,)
    assert tuple(int((lab == k).sum()) for k in (0, 1, 2)) == expected


def test_labels_only_012_and_partition():
    lab = split_labels(1000, RATIOS, np.random.default_rng(1))
    assert set(np.unique(lab).tolist()) <= {0, 1, 2}
    assert sum(int((lab == k).sum()) for k in (0, 1, 2)) == 1000
    # 무작위로 섞였는지(앞 700개가 모두 train이면 섞지 않은 것)
    assert not np.all(lab[:700] == 0)


def test_reproducible():
    a = split_labels(500, RATIOS, np.random.default_rng(3))
    b = split_labels(500, RATIOS, np.random.default_rng(3))
    c = split_labels(500, RATIOS, np.random.default_rng(4))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
