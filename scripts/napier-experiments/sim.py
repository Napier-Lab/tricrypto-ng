import json
from math import prod
from enum import Enum
import pandas as pd
import boa
from pprint import pprint
from eth_utils import to_checksum_address
import pytest
from yield_metapool import NapierYieldMetaCurveV2


def mint_for_testing(token_contract, addr, amount, mint_eth=False):

    addr = to_checksum_address(addr)

    if token_contract.symbol() == "WETH":
        boa.env.set_balance(addr, boa.env.get_balance(addr) + amount)
        if not mint_eth:
            with boa.env.prank(addr):
                token_contract.deposit(value=amount)
    else:
        token_contract.eval(f"self.totalSupply += {amount}")
        token_contract.eval(f"self.balanceOf[{addr}] += {amount}")
        token_contract.eval(f"log Transfer(empty(address), {addr}, {amount})")


class Action(Enum):
    AddLiquidity = "AddLiquidity"
    RemoveLiquidity = "RemoveLiquidity"
    SwapPTExactIn = "SwapPTExactIn"
    SwapUnderlyingExactIn = "SwapUnderlyingExactIn"


ONE_YEAR = 60 * 60 * 24 * 365
# reserve states when pool starts; UNDERLYING:PT1:PT2:PT3 = 3:1:1:1
INITIAL_UNDERLYING_LIQUIDITY = 1000 * 10**18
# https://curve.fi/#/ethereum/pools/factory-crypto-91/deposit
INITIAL_PRICES = [10**18, 10**18, 10**18]  # 1:1:1
PARAMS = {
    # tricrypto
    # "A": 135 * 3**3 * 10000,
    # "gamma": int(7e-5 * 1e18),
    # "mid_fee": int(4e-4 * 1e10),
    # "out_fee": int(4e-3 * 1e10),
    # "allowed_extra_profit": 2 * 10**12,
    # "fee_gamma": int(0.02 * 1e18),
    "adjustment_step": int(0.0015 * 1e18),
    "ma_time": 866,  # 600 seconds / ln(2)
    "initial_prices": INITIAL_PRICES[1:],
    # modified
    # TODO: check this
    # "A": int(2.5 * 135 * 3**3 * 10000),  # MAX = 1000 * 3**3 * 10000
    "A": int(27000000),  # MAX = 1000 * 3**3 * 10000
    "gamma": int(0.02 * 1e18),
    # "mid_fee": int(4e-3 * 1e10),
    "mid_fee": int(3000000),
    # "out_fee": int(4e-2 * 1e10),
    "out_fee": int(22000000),
    "allowed_extra_profit": int(0.00000001 * 1e18),
    "fee_gamma": int(0.2 * 1e18),
    # "adjustment_step": int(0.000015 * 1e18),
    "g": 1,
}


def _setup_pool():

    deployer = boa.env.generate_address()
    fee_receiver = boa.env.generate_address()
    user = boa.env.generate_address()

    with boa.env.prank(deployer):

        # tokens:
        weth = boa.load("contracts/mocks/WETH.vy")
        usd = boa.load("contracts/mocks/ERC20Mock.vy", "USD", "USD", 18)
        pt1 = boa.load("contracts/mocks/ERC20Mock.vy", "PT1", "PT1", 18)
        pt2 = boa.load("contracts/mocks/ERC20Mock.vy", "PT2", "PT2", 18)
        pt3 = boa.load("contracts/mocks/ERC20Mock.vy", "PT3", "PT3", 18)

        coins = [pt1, pt2, pt3]

        math_contract = boa.load("contracts/main/CurveCryptoMathOptimized3.vy")

        gauge_interface = boa.load_partial("contracts/main/LiquidityGauge.vy")
        gauge_implementation = gauge_interface.deploy_as_blueprint()

        amm_interface = boa.load_partial(
            "contracts/main/CurveTricryptoOptimizedWETH.vy"
        )
        amm_implementation = amm_interface.deploy_as_blueprint()

        views = boa.load("contracts/main/CurveCryptoViews3Optimized.vy")

        factory = boa.load(
            "contracts/main/CurveTricryptoFactory.vy",
            fee_receiver,
            deployer
        )

        factory.set_pool_implementation(amm_implementation, 0)
        factory.set_gauge_implementation(gauge_implementation)
        factory.set_views_implementation(views)
        factory.set_math_implementation(math_contract)

        _swap = factory.deploy_pool(
            "Curve.fi USDC-PT1-PT2-PT3",
            "PT1PT2PT3",
            [coin.address for coin in coins],
            weth,
            0,  # <-------- 0th implementation index
            PARAMS["A"],
            PARAMS["gamma"],
            PARAMS["mid_fee"],
            PARAMS["out_fee"],
            PARAMS["fee_gamma"],
            PARAMS["allowed_extra_profit"],
            PARAMS["adjustment_step"],
            PARAMS["ma_time"],
            PARAMS["initial_prices"],
        )
        swap = amm_interface.at(_swap)

    # set up Napier pool
    napier_pool_address = boa.env.generate_address()
    yield_metapool = NapierYieldMetaCurveV2(
        usd, swap, coins, napier_pool_address, swap, g=PARAMS["g"]
    )

    # add 1000 of each token to the pool
    # quantities = _get_deposit_amounts(10**4, INITIAL_PRICES, coins)
    quantities = [10**8 * 10**18, 10**8 * 10**18, 10**8 * 10**18, 10**8 * 10**18]
    for coin, quantity in zip(coins + [usd], quantities):
        # mint coins for user:
        user_balance = coin.balanceOf(user)
        mint_for_testing(coin, user, quantity)
        assert coin.balanceOf(user) == user_balance + quantity

        # approve crypto_swap to trade coin for user:
        with boa.env.prank(user):
            coin.approve(yield_metapool.address, 2**256 - 1)

    # USD:3000, PT1:1000, PT2:1000, PT3:1000
    yield_metapool._initializeLiquidity(INITIAL_UNDERLYING_LIQUIDITY, user)
    assert yield_metapool.balanceOf(user) == int(INITIAL_UNDERLYING_LIQUIDITY / 3)
    assert swap.balanceOf(yield_metapool.address) > 0

    # we need to disable loss calculation since there is no fee involved
    # and swaps will not result in vprice going up. to do this, ramp
    # up but do not actually ramp.
    # with boa.env.prank(deployer):
    #     swap.ramp_A_gamma(
    #         swap.A(),
    #         swap.gamma(),
    #         boa.env.vm.state.timestamp + ONE_YEAR,
    #     )

    swapper = boa.env.generate_address()
    quantities = [10**8 * 10**18, 10**8 * 10**18, 10**8 * 10**18, 10**8 * 10**18]
    for coin, quantity in zip(coins + [usd], quantities):
        # mint coins for swapper:
        mint_for_testing(coin, swapper, quantity)
        # approve crypto_swap to trade coin for swapper:
        with boa.env.prank(swapper):
            coin.approve(yield_metapool.address, 2**256 - 1)

    print("coin", [coin.address for coin in coins])
    print("usd", usd.address)

    return swap, yield_metapool, usd, coins, views, swapper


@pytest.fixture
def setup_pool():
    yield _setup_pool()


def test_scenario(setup_pool):
    # load scenario
    with open("scripts/napier-experiments/scenarios/scenario2.json", "r") as file:
        scenarios = json.load(file)
    # set up pool
    swap, yield_metapool, usd, coins, views, swapper = setup_pool
    bals = _get_reserves(yield_metapool)
    print('Initial Balances:')
    pprint(bals)

    def _to_addr(name):
        return {
            "usd": usd.address,
            "pt1": coins[0].address,
            "pt2": coins[1].address,
            "pt3": coins[2].address,
        }[name]

    data = {
        "time_to_maturity": [],
        "bal_pt1": [],
        "bal_pt2": [],
        "bal_pt3": [],
        "bal_underlying": [],
        "bal_ptidx": [],
        "price_pt1": [],
        "price_pt2": [],
        "price_pt3": [],
        "ir_idx": [],
        "ir_pt1": [],
        "ir_pt2": [],
        "ir_pt3": [],
    }
    # iterate over scenarios
    while (yield_metapool.amm_math.time_to_maturity() > 0):
        time_to_maturity = yield_metapool.amm_math.time_to_maturity()
        # filter out trades that are not to be executed at this time
        trades = list(filter(
            lambda trade: trade['time_to_maturity'] >= time_to_maturity
            and time_to_maturity + 0.01 > trade["time_to_maturity"], scenarios
        ))
        if len(trades) == 0:
            print(f"No action at time {time_to_maturity}")
        else:
            # get the trade to be executed
            trade = trades[-1]
            action = Action[trade["action"]]
            # execute the trade
            print(f"Action: {action} at time {time_to_maturity}")
            if action == Action.AddLiquidity:
                yield_metapool.addLiquidityFromShare(trade["share"], swapper)
            elif action == Action.RemoveLiquidity:
                yield_metapool.removeLiquidityFromShare(trade["share"], swapper)
            elif action == Action.SwapPTExactIn or action == Action.SwapUnderlyingExactIn:
                amount_out = yield_metapool.swapExactIn(
                    _to_addr(trade["coin_in"]),
                    _to_addr(trade["coin_out"]),
                    trade["amount_in"],
                    swapper)
                print(
                    f"effective price: {_get_eff_price(trade['coin_in'], trade['coin_out'], trade['amount_in'], amount_out)}"
                )
            pprint(_get_reserves(yield_metapool))
        # update data
        data["time_to_maturity"].append(time_to_maturity)
        data["ir_idx"].append(yield_metapool.r_idx())
        data["bal_underlying"].append(usd.balanceOf(yield_metapool.address))
        data["bal_ptidx"].append(yield_metapool.curve_v2.balanceOf(yield_metapool.address))
        for i, coin in enumerate(yield_metapool.internal_coins):
            marginal_ir = _get_marginal_interest_rate(yield_metapool, i)
            data[f"price_pt{i+1}"].append(None)
            data[f"ir_pt{i+1}"].append(marginal_ir)
            data[f"bal_pt{i+1}"].append(yield_metapool.curve_v2.balances(i))
        # update block timestamp
        boa.env.time_travel(int(0.01 * ONE_YEAR))

    # save data
    data = pd.DataFrame(data)
    data.to_csv("data/marginal_ir.csv", index=False)


# def test_efficiency(setup_pool):
#     # set up pool
#     time_to_maturity = 0.9999
#     market_ir = 0.04
#     desired_ir = 0.05

#     # if time_to_maturity is 1, swap will fail (not sure this is legit)
#     boa.env.time_travel(int((1 - time_to_maturity) * ONE_YEAR))
#     swap, yield_metapool, usd, coins, views, swapper = setup_pool

#     # push up the interest rate up to the market interest rate
#     amount_in = 1 * 10**18
#     while (True):
#         amount_out = yield_metapool.swapExactIn(coins[0].address, usd.address, amount_in, swapper)
#         ir = _get_marginal_interest_rate(yield_metapool, 0)
#         print(f"ir: {ir}")
#         print(f"effective price: {_get_eff_price('pt1', 'usd', amount_in, amount_out)}")
#         if ir > market_ir:
#             market_ir = ir
#             break
#     print("market state:")
#     pprint(_get_reserves(yield_metapool))

#     # push up the interest rate up to the desired interest rate
#     amount_swap = 0
#     while (True):
#         amount_swap += amount_in
#         yield_metapool.swapExactIn(coins[0].address, usd.address, amount_in, swapper)
#         ir = _get_marginal_interest_rate(yield_metapool, 0)
#         print(f"ir: {ir}")
#         if ir > desired_ir:
#             desired_ir = ir
#             break

#     print("Result:\n",
#           "coin_in: pt1\n",
#           "coin_out: usd\n",
#           f"market_ir [%]: {market_ir*100}\n",
#           f"desired_ir [%]: {desired_ir*100}\n",
#           f"amount_swap [pt1]: {amount_swap/1e18}"
#           )
#     pprint(_get_reserves(yield_metapool))


def _get_marginal_interest_rate(yield_metapool: NapierYieldMetaCurveV2, internal_coin_index):
    n = len(yield_metapool.internal_coins)
    # dived by 1e18. assume all coins have 18 decimals
    zs = [yield_metapool.curve_v2.balances(i) / 1e18 for i in range(n)]
    D = yield_metapool.curve_v2.D() / 1e18  # D has 18 decimals ??
    A = yield_metapool.curve_v2.A()  # A has 0 decimals
    K0 = (prod(zs)) / ((D / n) ** n)
    gamma = yield_metapool.curve_v2.gamma() / 1e18  # gamma is in 1e18
    share_idx = yield_metapool.curve_v2.totalSupply() / 1e18
    r_idx = yield_metapool.r_idx()
    time_to_maturity = yield_metapool.amm_math.time_to_maturity()
    return _calculate_marginal_ir_of_index(
        i=internal_coin_index, n=n, D=D, A=A, K0=K0, gamma=gamma, zs=zs, s_idx=share_idx, r_idx=r_idx, time_to_mat=time_to_maturity
    )


def _calculate_marginal_ir_of_index(i, n, D, A, K0, gamma, zs, s_idx, r_idx, time_to_mat):
    numerator_1th_term = n * D * (gamma + 1 - K0)**3 + n**(n + 1) * A * gamma**2 * \
        (sum(zs) - D) * (gamma + 1 + K0) * prod(zs)
    numerator_2nd_term = D**n * A * gamma**2 * K0 * (gamma + 1 - K0) * sum(zs)
    numerator = (numerator_1th_term + numerator_2nd_term) * zs[i]

    denominator_1th_term = (D * (gamma + 1 - K0)**3 + n**n * A * gamma**2 * (sum(zs) - D) * (gamma + 1 + K0)) * prod(zs)
    denominator_2nd_term = D**n * A * gamma**2 * K0 * (gamma + 1 - K0) * zs[i]
    # 3x because of the 3 coins
    # share is composed of 3 coins so we need to multiply by 3
    denominator = (denominator_1th_term + denominator_2nd_term) * (3 * s_idx)
    # XXX: i'm not sure if this is correct
    if denominator == 0:
        print("something is wrong. denominator is 0")
        return 0
    ri = (numerator / denominator)**(1 / time_to_mat) * (1 + r_idx) - 1
    return ri


def _get_curve_reserve(yield_metapool: NapierYieldMetaCurveV2):
    bals = {f"pt{i+1}": yield_metapool.curve_v2.balances(i) for i in range(3)}
    # curve reserves
    bals["pt1_comp"] = yield_metapool.getExtReserve(0)
    bals["pt2_comp"] = yield_metapool.getExtReserve(1)
    bals["pt3_comp"] = yield_metapool.getExtReserve(2)
    return bals


def _get_reserves(yield_metapool: NapierYieldMetaCurveV2):
    curve_v2 = yield_metapool.curve_v2
    bals = _get_curve_reserve(yield_metapool)

    underlying = yield_metapool._coin_contracts[yield_metapool.coins[0]]
    ptidx = yield_metapool._coin_contracts[yield_metapool.coins[1]]

    # yield metapool reserves
    bals["underlying"] = underlying.balanceOf(yield_metapool.address)
    bals["ptidx"] = ptidx.balanceOf(yield_metapool.address)
    bals["underlying_comp"] = yield_metapool.getReserve(0)
    bals["ptidx_comp"] = yield_metapool.getReserve(1)
    # share
    bals["curve_tot_share"] = curve_v2.totalSupply()
    bals["yield_metapool_tot_share"] = yield_metapool.totalSupply()
    bals["yield_metapool_curve_share_bal"] = curve_v2.balanceOf(
        yield_metapool.address)
    return bals


def _get_eff_price(coin_in, coin_out, amount_in, amount_out):
    """
    Get effective price of a swap
    @return: effective price in units of underlying
    """
    effective_price = amount_in / amount_out
    if coin_in == "usd":
        return effective_price
    if coin_out == "usd":
        return 1 / effective_price
    else:
        raise ValueError("effective price between pts is not supported")
