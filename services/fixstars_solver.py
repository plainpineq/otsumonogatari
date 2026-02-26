from amplify import VariableGenerator, solve, FixstarsClient
import logging

def solve_with_fixstars(Q, api_key):
    """
    Fixstars Amplify SDKを使用してQUBOを解く
    """
    # 変数数を取得
    max_index = 0
    if not Q:
        return {"selected_indices": [], "energy": 0.0}
        
    for i, j in Q.keys():
        max_index = max(max_index, i, j)
    n = max_index + 1

    gen = VariableGenerator()
    x = gen.array("Binary", n)

    # QUBO式構築
    objective = 0
    for (i, j), val in Q.items():
        if i == j:
            objective += val * x[i]
        else:
            objective += val * x[i] * x[j]

    client = FixstarsClient(token=api_key)

    # v1.0.0+ の形式で実行
    result = solve(objective, client)
    
    if not result:
        raise RuntimeError("No solutions returned from Fixstars Amplify.")

    best = result.best
    values = best.values
    # v1では energy 属性ではなく objective 属性が一般的
    # ただし、互換性のためにチェックする
    energy = getattr(best, "objective", getattr(best, "energy", 0.0))

    # 選択された変数インデックス抽出
    selected_indices = [
        idx for idx in range(n)
        if values.get(idx) == 1
    ]

    return {
        "selected_indices": selected_indices,
        "energy": energy
    }
