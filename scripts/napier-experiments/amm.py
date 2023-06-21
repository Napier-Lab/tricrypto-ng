from typing import Dict, List
from amm_types import MathAMM, ERC20
import boa


class LpToken(ERC20):
    _balances = {}

    def balanceOf(self, addr):
        return self._balances.get(addr, 0)

    def totalSupply(self):
        return sum(self._balances.values())

    def mint(self, addr, amount):
        self._balances[addr] = self.balanceOf(addr) + amount

    def burn(self, addr, amount):
        if self.balanceOf(addr) < amount:
            raise Exception("Insufficient balance")
        self._balances[addr] = self.balanceOf(addr) - amount


class ModifiedCPSMM_Math(MathAMM):
    reserves: List[int]

    def __init__(self, underlying, principal_token, g, n_internal_coins) -> None:
        self.N_INTERNAL_COINS = n_internal_coins
        self.initial_time_to_maturity = g
        self.started_at = boa.env.vm.state.timestamp
        # 0: underlying, 1: principal token
        self.coins = [underlying, principal_token]
        self.reserves = [0, 0]
        self.g = g

    def swapExactIn(self, coin_in, coin_out, amount_in):
        if coin_in == coin_out:
            raise Exception("Same coin")
        amount_out = self._swapExactIn(coin_in, coin_out, amount_in)
        return amount_out

    def _swapExactIn(self, coin_in, coin_out, amount_in):
        # get reserves
        u_reserve = self.getReserve(0)
        scaled_pt_reserve = self.getReserve(1) * self.N_INTERNAL_COINS
        if coin_in == self.coins[0]:  # coin_in is underlying
            factor = self._oneSubTimeToMaturityMulG()
            inv_factor = 1 / factor if factor != 0 else 0
            # compute new reserve out
            new_u_reserve = u_reserve + amount_in
            new_scaled_pt_reserve = int((
                scaled_pt_reserve ** factor + u_reserve ** factor - new_u_reserve ** factor) ** inv_factor)
            amount_out = int((scaled_pt_reserve - new_scaled_pt_reserve) / self.N_INTERNAL_COINS)
        elif coin_in == self.coins[1]:  # coin_in is principal token
            factor = self._oneSubTimeToMaturityDivG()
            inv_factor = 1 / factor if factor != 0 else 0
            # compute new reserve out
            new_scaled_pt_reserve = scaled_pt_reserve + amount_in * self.N_INTERNAL_COINS
            new_u_reserve = int((
                scaled_pt_reserve ** factor + u_reserve ** factor - new_scaled_pt_reserve ** factor) ** inv_factor)
            amount_out = u_reserve - new_u_reserve
        else:
            raise Exception("Invalid coin")
        # update reserves
        new_pt_reserve = int(new_scaled_pt_reserve / self.N_INTERNAL_COINS)
        self.reserves[self._get_index(self.coins[0])] = new_u_reserve
        self.reserves[self._get_index(self.coins[1])] = new_pt_reserve
        # print("coin_in, coin_out :>>", coin_in, coin_out)
        # print("factor :>>", factor)
        # print("amount_in :>>", amount_in)
        # print("amount_out :>>", amount_out)
        # print("new_scaled_reserve0 // self.N_INTERNAL_COINS :>>",
        #       new_scaled_pt_reserve // self.N_INTERNAL_COINS)
        # print("new_scaled_reserve0 :>>", new_scaled_pt_reserve)
        # print("new_reserve1 :>>", new_u_reserve)
        if amount_out < 0:
            raise Exception("Negative amount out")
        if self.pt_price() < 0 or self.pt_price() > 1:
            raise Exception("Invalid price after swap")
        return int(amount_out)

    def addLiquidityFromShare(self, share):
        pass

    def time_to_maturity(self) -> int:
        ONE_YEAR = 365 * 24 * 60 * 60
        elapsed = boa.env.vm.state.timestamp - self.started_at
        time_to_maturity = self.initial_time_to_maturity - elapsed / ONE_YEAR
        if time_to_maturity < 0:
            raise Exception("Time to maturity is negative")
        return time_to_maturity

    def _oneSubTimeToMaturityDivG(self):
        return 1 - self.time_to_maturity() / self.g

    def _oneSubTimeToMaturityMulG(self):
        return 1 - self.time_to_maturity() * self.g

    def getReserve(self, coin) -> int:
        index = coin if isinstance(coin, int) else self._get_index(coin)
        return self.reserves[index]

    def marginal_interest_rate(self) -> float:
        """Return the marginal interest rate of the principal token"""
        # 0: underlying, 1: principal token
        return 3 * self.reserves[1] / self.reserves[0] - 1

    def pt_price(self) -> float:
        return (self.reserves[0] / (3 * self.reserves[1])) ** self.time_to_maturity()
