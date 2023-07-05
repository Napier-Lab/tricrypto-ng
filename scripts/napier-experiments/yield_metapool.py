from typing import Dict, List
import boa
from eth_utils import to_checksum_address
from amm import MathAMM, LpToken, ERC20, ModifiedCPSMM_Math
from amm_types import CurveV2


class YieldMetaAMM(MathAMM, LpToken):
    amm_math: ModifiedCPSMM_Math
    address: str
    _coin_contracts: Dict[str, ERC20]
    _internal_coin_contracts: List[ERC20]

    def __init__(
            self,
            underlying: str,
            metacoin: str,
            internal_coins: List[str],
            amm_math,
            address) -> None:
        # NOTE:  0 is underlying, 1 is metacoin
        self.coins = [underlying, metacoin]
        self.internal_coins = internal_coins
        self.amm_math = amm_math
        self.address = to_checksum_address(address)

    def swapExactIn(
            self,
            coin_in: str,
            coin_out: str,
            amount_in: int,
            caller: str):
        caller = to_checksum_address(caller)
        coin_in = to_checksum_address(coin_in)
        coin_out = to_checksum_address(coin_out)
        if coin_in == coin_out:
            raise Exception("Same coin")
        if coin_in == self.coins[1]:
            raise NotImplementedError("Meta coin In not implemented")
        if coin_in == self.coins[0]:
            return self._swapUnderlyingExactIn(coin_out, amount_in, caller)
        if coin_in in self.internal_coins:
            if coin_out != self.coins[0]:
                raise NotImplementedError("Underlying Out is only implemented")
            return self._swapPTExactIn(coin_in, coin_out, amount_in, caller)
        raise Exception("Invalid coin in")

    def _swapPTExactIn(
            self,
            coin_in: str,
            coin_out: str,
            amount_in: int,
            caller: str):
        if amount_in < 0:
            raise Exception("Amount in must be positive")
        # convert coin_in to metacoin (Lp token) i.e. add liquidity
        # and swap metacoin to coin_out in amms
        amount_metacoin_in = self._addExternalLiquidityFromOneCoin(
            coin_in, amount_in, caller)
        amount_out = self.amm_math.swapExactIn(
            self.coins[1], coin_out, amount_metacoin_in)
        # transfer coin_out to caller
        self._transfer(coin_out, caller, amount_out)
        return amount_out

    def _swapUnderlyingExactIn(
            self,
            coin_out: str,
            amount_in: int,
            caller: str) -> int:
        if amount_in < 0:
            raise Exception("Amount in must be positive")
        coin_in = self.coins[0]
        # transfer coin_in=underlying to this
        self._transferFrom(coin_in, caller, self.address, amount_in)
        # swap underlying to metacoin in amms
        amount_metacoin_swapped = self.amm_math.swapExactIn(
            coin_in, self.coins[1], amount_in)
        # withdraw metacoin liquidity from external pool with one coin
        # transfer coin_out to caller
        print(f"proportion [%] :>> {amount_metacoin_swapped / self.getReserve(self.coins[1])*100}")
        amount_out = self._removeExternalLiquidityOneCoin(
            coin_out, amount_metacoin_swapped, caller)
        return amount_out

    def _initializeLiquidity(self, u_amount, caller):
        if self.totalSupply() != 0:
            raise Exception("Liquidity already initialized")
        n = len(self.internal_coins)
        pt_amount = int(u_amount / n)
        share = pt_amount
        # transfer amount of underlying
        self._transferFrom(
            self.coins[0],
            caller,
            self.address,
            u_amount)
        # transfer internal coins
        pt_amounts_in = [pt_amount] * n
        for coin, pt_amount in zip(self.internal_coins, pt_amounts_in):
            self._transferFrom(
                coin,
                caller,
                self.address,
                pt_amount)
        # add liquidity to external pool
        with boa.env.prank(self.address):
            minted = self.curve_v2.add_liquidity(pt_amounts_in, 0)
        print(f"expected, minted :>> {share}, {minted}")

        # mint LP token
        self.amm_math.reserves[0] = u_amount
        self.amm_math.reserves[1] = minted
        self.mint(caller, share)
        return minted

    def addLiquidityFromShare(self, share, caller) -> int:
        if self.totalSupply() == 0:
            raise Exception(
                "No liquidity in pool. Total supply zero is not supported yet")
        # convert share to ratio
        proportion = share / self.totalSupply()

        # transfer underlying
        u_amount_in = int(proportion * self.getReserve(self.coins[0]))
        self._transferFrom(
            self.coins[0],
            caller,
            self.address,
            u_amount_in)
        # add liquidity to external pool
        inner_share = int(proportion * self.getReserve(self.coins[1]))
        minted = self._addExternalLiquidityFromShare(inner_share, caller)
        # mint LP token
        self.amm_math.reserves[0] += u_amount_in
        self.amm_math.reserves[1] += minted
        self.mint(caller, share)

    def removeLiquidityFromShare(self, share, caller) -> int:
        if self.totalSupply() == 0:
            raise Exception("No liquidity in pool")
        # convert share to ratio
        proportion = share / self.totalSupply()
        # transfer underlying
        u_amount_out = int(proportion * self.getReserve(self.coins[0]))
        self._transfer(
            self.coins[0],
            caller,
            u_amount_out)
        # remove liquidity from external pool
        inner_share = int(proportion * self.getReserve(self.coins[1]))
        burned_amounts = self._removeExternalLiquidityFromShare(inner_share, caller)
        # burn LP token
        self.amm_math.reserves[0] -= u_amount_out
        self.amm_math.reserves[1] -= inner_share
        self.burn(caller, share)

        return share
    # -------------------------------- EXTERNAL POOL OPERATION (VIRTUAL) -----

    def _addExternalLiquidityFromOneCoin(
            self, coin_in, amount_in, caller) -> int:
        pass

    def _removeExternalLiquidityOneCoin(
            self, coin_withdraw, inner_share, caller) -> int:
        pass

    def _addExternalLiquidityFromShare(self, share, caller) -> int:
        pass

    def _removeExternalLiquidityFromShare(self, inner_share, caller) -> List[int]:
        pass

    def getExtReserve(self, coin):
        pass

    def getReserve(self, coin):
        return self.amm_math.getReserve(coin)

    def _get_internal_coin_index(self, coin):
        return self.internal_coins.index(to_checksum_address(coin))

    def _transfer(self, _coin, _to, _value):
        pass

    def _transferFrom(self, _coin, _from, _to, _value):
        pass


class NapierYieldMetaCurveV2(YieldMetaAMM):
    curve_v2: CurveV2
    amm: ModifiedCPSMM_Math

    def __init__(
            self,
            underlying_contract: ERC20,
            metacoin_contract: ERC20,
            internal_coin_contracts: List[ERC20],
            address: str,
            curve_v2,
            g) -> None:
        uAddr = to_checksum_address(underlying_contract.address)
        metacoin_addr = to_checksum_address(metacoin_contract.address)
        # save the contracts
        self._coin_contracts = {
            uAddr: underlying_contract, metacoin_addr: metacoin_contract}
        self._internal_coin_contracts = {
            to_checksum_address(
                internal_coin_contracts[i].address): internal_coin_contracts[i] for i in range(
                len(internal_coin_contracts))}
        amm = ModifiedCPSMM_Math(
            underlying=underlying_contract.address,
            principal_token=metacoin_contract.address,
            g=g,
            n_internal_coins=len(internal_coin_contracts))
        # initialize the pool
        super().__init__(
            underlying=uAddr,
            metacoin=metacoin_addr,
            internal_coins=list(self._internal_coin_contracts.keys()),
            amm_math=amm,
            address=address)
        self.curve_v2 = curve_v2

        # approve all coins to be spent by curve v2
        for coin in self._internal_coin_contracts.values():
            with boa.env.prank(self.address):
                coin.approve(self.curve_v2.address, 2**256 - 1)

    # ---------------------------------- EXTERNAL POOL OPERATION -------------

    def _addExternalLiquidityFromOneCoin(
            self, coin_in, amount_in, caller) -> int:
        # transfer coin_in to this
        self._transferFrom(coin_in, caller, self.address, amount_in)

        amounts_in = [0] * len(self.internal_coins)
        index = self._get_internal_coin_index(coin_in)
        amounts_in[index] = amount_in
        with boa.env.prank(self.address):
            minted = self.curve_v2.add_liquidity(amounts_in, 0)
        return minted

    def _addExternalLiquidityFromShare(self, inner_share, caller) -> int:
        total_supply = self.curve_v2.totalSupply()
        # proportion of each coin in the pool
        xp = [self.curve_v2.balances(i)
              for i in range(len(self.internal_coins))]
        amounts_in = [int(x * inner_share / total_supply) for x in xp]
        # transfer internal coins instead of metacoin
        for amount, internal_coin in zip(amounts_in, self.internal_coins):
            self._transferFrom(
                internal_coin,
                caller,
                self.address,
                amount)
        with boa.env.prank(self.address):
            minted = self.curve_v2.add_liquidity(amounts_in, 0)
        print(f"expected, minted :>> {inner_share}, {minted}")
        return minted

    def _removeExternalLiquidityFromShare(self, inner_share, caller) -> List[int]:
        # remove liquidity and
        # transfer internal coins instead of metacoin
        with boa.env.prank(self.address):
            burned_amounts = self.curve_v2.remove_liquidity(inner_share, [0] * len(self.internal_coins), False, caller)
        return burned_amounts

    def _removeExternalLiquidityOneCoin(
            self, coin_withdraw, inner_share, caller) -> int:
        i = self._get_internal_coin_index(coin_withdraw)
        # expected_amount_out = self.curve_v2.calc_withdraw_one_coin(inner_share, i)
        with boa.env.prank(self.address):
            amount_out = self.curve_v2.remove_liquidity_one_coin(inner_share, i, 0, False, caller)
        return amount_out

    def getExtReserve(self, coin):
        i = coin if isinstance(
            coin, int) else self._get_internal_coin_index(coin)
        return self.curve_v2.balances(i)

    def r_idx(self):
        return self.amm_math.marginal_interest_rate()

    # ---------------------------------- TRANSFER HELPERS --------------------

    def _transfer(self, _coin: str, _to, _value):
        with boa.env.prank(self.address):
            toErc20(_coin).transfer(_to, _value)

    def _transferFrom(self, _coin: str, _from, _to, _value):
        with boa.env.prank(self.address):
            toErc20(_coin).transferFrom(_from, _to, _value)


def toErc20(coin):
    return boa.load_partial(
        "contracts/main/ERC20Mock.vy").at(to_checksum_address(coin))
