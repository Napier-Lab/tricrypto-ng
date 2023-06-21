from typing import Dict, List, Any


class MathAMM:
    coins: List[Any]

    def swapExactIn(self, coin_in, coin_out, amount_in):
        pass

    def addLiquidityFromShare(self, share):
        pass

    def _get_index(self, coin_like):
        return self.coins.index(self._get_coin(coin_like))

    def _get_coin(self, index_like):
        if isinstance(index_like, int):
            return self.coins[index_like]
        if index_like in self.coins:
            return index_like
        raise Exception("Invalid coin")


class ERC20:
    address: str

    def balanceOf(self, addr) -> int:
        pass

    def transfer(self, addr, amount):
        pass

    def transferFrom(self, _from, to, value):
        pass


class CurveV2:
    address: str

    def add_liquidity(self, amounts, min_mint_amount=0):
        pass

    def remove_liquidity(self, amounts):
        pass
