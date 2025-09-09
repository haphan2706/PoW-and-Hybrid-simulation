from dataclasses import dataclass, field
from typing import List

@dataclass
class Tx:
    frm: int
    to: int
    amount: int
    nonce: int
    tid: str

@dataclass
class Block:
    parent: str
    height: int
    proposer: int
    algo: str
    difficulty: int
    stake_epoch: int
    rnd_tag: str
    nonce: int
    txs: List[Tx]
    bhash: str
    work: int

@dataclass(order=True)
class Event:
    t_ms: int
    eid: int
    kind: str = field(compare=False)
    data: dict = field(compare=False, default_factory=dict)
