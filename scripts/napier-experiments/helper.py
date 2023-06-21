# N_COINS = 3
# PRECISION = 10**18  # <------- The precision to convert to.


# def _xps(swap, amounts: List[int]):
#     precisions = swap.precisions()
#     price_scale = swap.price_scale()
#     xp = [swap.balances(i) for i in range(N_COINS)]
#     # -------------------------------------- Update balances and calculate xp.
#     xp_old = xp[:]
#     for i in range(N_COINS):
#         xp[i] += amounts[i]

#     xp[0] *= precisions[0]
#     xp_old[0] *= precisions[0]
#     for i in range(1, N_COINS):
#         xp[i] = xp[i] * price_scale[i - 1] * precisions[i] / PRECISION
#         xp_old[i] = xp_old[i] * price_scale[i - 1] * precisions[i] / PRECISION
#     return xp_old, xp

# def _calc_amounts_in_from_share(swap,share):
#     MATH = swap.math()
#     A_gamma = [swap.A(), swap.gamma()]
#     xp_old, xp = _xps(swap)
#     if swap.future_A_gamma_time() > boa.env.vm.state.timestamp:
#         # ----- Recalculate the invariant if A or gamma are undergoing a ramp.
#         old_D = MATH.newton_D(A_gamma[0], A_gamma[1], xp_old, 0)
#     else:
#         old_D = swap.D()

#     D = MATH.newton_D(A_gamma[0], A_gamma[1], xp, 0)
#     token_supply = swap.totalSupply()
#     if old_D > 0:
#         d_token = token_supply * D / old_D - token_supply
#     else:
#         # <------------------------- Making initial
#         d_token = swap.internal._get_xcp(D)
#     return d_token
    
