import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_method_router40 import interval,wilson

def test_wilson_known_bounds():
    low,high=wilson(9,40)
    assert abs(low-12.316091)<.0001 and abs(high-37.503097)<.0001

def test_zero_solve_ratios_not_silently_dropped_when_material():
    assert interval([1,2,3,float('inf')]) is None
    assert interval([1]*999+[float('nan')])==[1,1]

def test_bootstrap_quantiles():
    np.testing.assert_allclose(interval(list(range(101))),[2.5,97.5])
