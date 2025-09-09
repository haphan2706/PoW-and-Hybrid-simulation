from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Config:
    seed: str = "seed-0"
    algo: str = "pow"
    k_final: int = 4
    n_nodes: int = 5
    base_delay_ms: int = 40
    jitter_ms: int = 60
    sim_time_limit_ms: int = 12000
    target_block_ms: int = 250
    pow_D: int = 2**18
    hybrid_D: int = 2**10
    partition_start_ms: Optional[int] = None
    partition_end_ms: Optional[int] = None
    partition_groups: Optional[List[List[int]]] = None
    tx_rate_per_node_per_sec: float = 2.0
    init_balance: int = 1000
    log_file: str = "log.jsonl"
