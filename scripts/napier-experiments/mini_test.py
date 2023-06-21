import pytest
from sim import ONE_YEAR, _setup_pool, _get_reserves
import boa
from pprint import pprint
from eth_utils import to_checksum_address
from amm import ModifiedCPSMM_Math
from yield_metapool import NapierYieldMetaCurveV2


# Each test should be executed isolated from the others.
# python -m pytest -s tests/boa/napier-experiments/mini_test.py::test_xxx

@pytest.fixture
def setup_pool():
    return _setup_pool()


@pytest.fixture
def swap(setup_pool):
    return setup_pool[0]


@pytest.fixture
def yield_metapool(setup_pool):
    return setup_pool[1]


@pytest.fixture
def usd(setup_pool):
    return setup_pool[2]


@pytest.fixture
def coins(setup_pool):
    return setup_pool[3]


@pytest.fixture
def swapper(setup_pool):
    return setup_pool[5]


def test_time_to_maturity(yield_metapool):
    cpsmm = yield_metapool.amm_math
    assert cpsmm.time_to_maturity() == 1
    boa.env.time_travel(int(0.01 * ONE_YEAR))
    assert cpsmm.time_to_maturity() == 0.99
    boa.env.time_travel(int(0.09 * ONE_YEAR))
    assert cpsmm.time_to_maturity() == 0.9
    boa.env.time_travel(int(0.9 * ONE_YEAR))
    assert cpsmm.time_to_maturity() == 0


def test_setup_ok(swap, yield_metapool, usd, coins):
    share = yield_metapool.totalSupply()
    bal0 = usd.balanceOf(yield_metapool.address)
    bal1 = swap.balanceOf(yield_metapool.address)
    assert share > 0 and share == bal1
    assert bal0 == 3 * bal1


def test_swap_pt(swap, yield_metapool, usd, coins, swapper):
    bals_before = _get_reserves(yield_metapool)
    pprint(bals_before)

    boa.env.time_travel(int(0.01 * ONE_YEAR))

    yield_metapool.swapExactIn(
        coins[0].address, usd.address, 50 * 10**18, swapper
    )
    bals_after = _get_reserves(yield_metapool)
    pprint(bals_after)
    assert yield_metapool.pt_price() < 1
    assert bals_after['underlying'] < bals_before['underlying']
    assert bals_after['pt1'] > bals_before['pt1']
    assert bals_after['pt2'] == bals_before['pt2']
    assert bals_after['pt3'] == bals_before['pt3']

"""
Action: Action.SwapUnderlyingExactIn at time 0.20999999999999996
{'curve_tot_share': 1026666118030194372717,
    'pt1': 1050000000000000000000,
    'pt1_comp': 1050000000000000000000,
    'pt2': 1030000000000000000000,
    'pt2_comp': 1030000000000000000000,
    'pt3': 1000000000000000000000,
    'pt3_comp': 1000000000000000000000,
    'ptidx': 1026666051364407278790,
    'ptidx_comp': 1026666051364407345152,
    'underlying': 2922014627248912990208,
    'underlying_comp': 2922014627248912990208,
    'yield_metapool_curve_share_bal': 1026666051364407278790,
    'yield_metapool_tot_share': 1000000000000000000000}
amount_metacoin_swapped :>> 337015957703404224
proportion :>> 0.00032837028484715403
Loss
"""
def test_swap_underlying(swap, yield_metapool, usd, coins, swapper):
    boa.env.time_travel(int(0.01 * ONE_YEAR))

    yield_metapool.swapExactIn(
        coins[0].address, usd.address, 100 * 10**18, swapper
    )

    bals_before = _get_reserves(yield_metapool)
    pprint(bals_before)

    yield_metapool.swapExactIn(
        usd.address, coins[0].address, 50 * 10**18, swapper
    )
    bals_after = _get_reserves(yield_metapool)
    pprint(bals_after)
    assert bals_after['underlying'] > bals_before['underlying']
    assert bals_after['pt1'] < bals_before['pt1']
    assert bals_after['pt2'] == bals_before['pt2']
    assert bals_after['pt3'] == bals_before['pt3']


def test_liquidity(swap, yield_metapool, usd, coins, swapper):
    bals_before = _get_reserves(yield_metapool)
    pprint(bals_before)
    tot_share = yield_metapool.totalSupply()

    boa.env.time_travel(int(0.01 * ONE_YEAR))

    yield_metapool.addLiquidityFromShare(tot_share // 2, swapper)
    bals_after_add = _get_reserves(yield_metapool)
    pprint(bals_after_add)

    assert yield_metapool.totalSupply() == 1.5 * tot_share
    assert bals_after_add["pt1"] == 1.5 * bals_before["pt1"]
    assert bals_after_add["pt2"] == 1.5 * bals_before["pt2"]
    assert bals_after_add["pt3"] == 1.5 * bals_before["pt3"]
    assert bals_after_add["ptidx"] == pytest.approx(1.5 * bals_before["ptidx"], abs=0.001 * 1e18)
    assert bals_after_add["underlying"] == pytest.approx(1.5 * bals_before["underlying"], abs=0.001 * 1e18)

    yield_metapool.removeLiquidityFromShare(
        tot_share // 2, swapper
    )
    bals_after_remove = _get_reserves(yield_metapool)
    pprint(bals_after_remove)

    assert yield_metapool.totalSupply() == tot_share
    assert bals_after_remove["pt1"] == pytest.approx(bals_before["pt1"], abs=0.001 * 1e18)
    assert bals_after_remove["pt2"] == pytest.approx(bals_before["pt2"], abs=0.001 * 1e18)
    assert bals_after_remove["pt3"] == pytest.approx(bals_before["pt3"], abs=0.001 * 1e18)
    assert bals_after_remove["ptidx"] == pytest.approx(bals_before["ptidx"], abs=0.001 * 1e18)
    assert bals_after_remove["underlying"] == pytest.approx(bals_before["underlying"], abs=0.001 * 1e18)
