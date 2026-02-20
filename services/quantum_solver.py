from typing import Dict, Tuple, List
import dimod
from dimod.reference.samplers import SimulatedAnnealingSampler


def solve_qubo_classical(
    Q: Dict[Tuple[int, int], float],
    num_reads: int = 200
):
    """
    古典シミュレーテッドアニーリングでQUBOを解く
    """
    bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
    sampler = SimulatedAnnealingSampler()
    sampleset = sampler.sample(bqm, num_reads=num_reads)
    return sampleset.first


def decode_onehot(
    sample: Dict[int, int],
    label_count: int = 12
) -> List[int]:
    """
    72bit One-hot解を元の0-5整数12個へ復元
    """
    values = []
    for i in range(label_count):
        start = i * 6
        bits = [sample.get(start + k, 0) for k in range(6)]
        if 1 in bits:
            values.append(bits.index(1))
        else:
            values.append(0)
    return values


def solve_and_decode(
    Q: Dict[Tuple[int, int], float],
    label_count: int = 12,
    num_reads: int = 200
) -> List[int]:
    """
    QUBOを解き、0-5評価値のリストを返す
    """
    result = solve_qubo_classical(Q, num_reads=num_reads)
    decoded = decode_onehot(result.sample, label_count)
    return decoded


def test_quantum_solver():
    """
    単体テスト（既存処理には影響しない）
    """
    from services.scoring import generate_onehot_qubo

    dummy_target = [3] * 12
    dummy_weights = {
        "CategoryA": 1.0,
        "CategoryB": 1.0,
        "CategoryC": 1.0
    }

    label_order = [
        "CategoryA:Item1", "CategoryA:Item2", "CategoryA:Item3", "CategoryA:Item4",
        "CategoryB:Item1", "CategoryB:Item2", "CategoryB:Item3", "CategoryB:Item4",
        "CategoryC:Item1", "CategoryC:Item2", "CategoryC:Item3", "CategoryC:Item4",
    ]

    Q = generate_onehot_qubo(
        dummy_target,
        dummy_weights,
        label_order
    )

    solution = solve_and_decode(Q)

    print("=== Quantum Solver Test ===")
    print("Decoded solution:", solution)
