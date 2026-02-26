import os
from amplify import VariableGenerator, solve, FixstarsClient

# APIキーは環境変数 AMPLIFY_API_KEY から取得するか、直接書き換えてください
API_KEY = "AE/5d9wubGE7Zs7XklKGuReJbYDLnehldoQ"

if API_KEY == "YOUR_API_KEY_HERE":
    print("Warning: API_KEY is not set. Please set AMPLIFY_API_KEY environment variable or edit the script.")

gen = VariableGenerator()
x = gen.array("Binary", 2)

# 最小QUBO: x0 + x1 - 2*x0*x1
objective_func = x[0] + x[1] - 2 * x[0] * x[1]

# v1.0.0+ の形式
client = FixstarsClient(token=API_KEY)

try:
    result = solve(objective_func, client)
    
    if not result:
        print("No solutions found.")
    else:
        best = result.best
        print(f"Values: {best.values}")
        
        # 属性の自動判別
        if hasattr(best, "objective"):
            print(f"Objective: {best.objective}")
        elif hasattr(best, "energy"):
            print(f"Energy: {best.energy}")
        else:
            print("\n!!! 'objective' も 'energy' も見つかりませんでした !!!")
            print("利用可能な属性一覧:")
            print(dir(best))

except Exception as e:
    print(f"Error: {e}")
