from typing import Dict, List, Tuple
from config import Config
from logger import FileLogger
from network import Network
from models import Tx, Block
from utils import H_hex, H_int

class Node:
    def __init__(self, nid: int, cfg: Config, net: Network, logger: FileLogger):
        self.id = nid
        self.cfg = cfg
        self.net = net
        self.log = logger

        self.blocks: Dict[str, Block] = {}
        self.children: Dict[str, List[str]] = {}
        self.best_head: str = ""

        ghash = H_hex(cfg.seed.encode(), b"genesis")
        genesis = Block(
            parent="",
            height=0,
            proposer=-1,
            algo="genesis",
            difficulty=1,
            stake_epoch=0,
            rnd_tag="",
            nonce=0,
            txs=[],
            bhash=ghash,
            work=1,
        )
        self.blocks[ghash] = genesis
        self.children[ghash] = []
        self.best_head = ghash

        self.mempool: List[Tx] = []
        self.nonce: Dict[int, int] = {i: 0 for i in range(cfg.n_nodes)}
        self.balance: Dict[int, int] = {i: cfg.init_balance for i in range(cfg.n_nodes)}

        self.final_height = 0
        self.final_block_by_h: Dict[int, str] = {0: ghash}

        self.stake: Dict[int, int] = {i: cfg.init_balance for i in range(cfg.n_nodes)}

        self.pow_epoch = 0
        self.hybrid_epoch = 0
        self.nonce_salt = 1000003 * (1 + self.id)

        self.schedule_tick(0)
        self.schedule_work(0)

    def emit(self, evtype: str, **fields):
        self.log({
            "t": self.net.time_ms,
            "node": self.id,
            "type": evtype,
            **fields
        })

    def head_work_height(self, bhash: str) -> Tuple[int, int]:
        w = 0
        h = 0
        cur = bhash
        while cur:
            b = self.blocks[cur]
            w += b.work
            h = b.height
            cur = b.parent
        return (w, h)

    def better(self, a: str, b: str) -> bool:
        wa, ha = self.head_work_height(a)
        wb, hb = self.head_work_height(b)
        if wa != wb:
            return wa > wb
        if ha != hb:
            return ha > hb
        return int(a, 16) < int(b, 16)

    def attach_block(self, blk: Block):
        if blk.bhash in self.blocks:
            return
        if blk.parent not in self.blocks:
            return
        self.blocks[blk.bhash] = blk
        self.children.setdefault(blk.parent, []).append(blk.bhash)
        self.children.setdefault(blk.bhash, [])

        if self.better(blk.bhash, self.best_head):
            old = self.best_head
            self.best_head = blk.bhash
            self.emit("reorg", old_head=old, new_head=self.best_head)

        self.update_finality()

    def update_finality(self):
        k = self.cfg.k_final
        chain: List[str] = []
        cur = self.best_head
        while cur:
            chain.append(cur)
            cur = self.blocks[cur].parent
        chain.reverse()

        if not chain:
            return

        final_idx = len(chain) - 1 - k
        if final_idx <= 0:
            return

        for i in range(self.final_height + 1, final_idx + 1):
            bh = chain[i]
            if i in self.final_block_by_h and self.final_block_by_h[i] != bh:
                raise RuntimeError(f"Finality conflict at height {i}")
            self.final_block_by_h[i] = bh
            self.final_height = i
            self.emit("finalize", height=i, bhash=bh)
        self.check_final_chain_state()

    def check_final_chain_state(self):
        bal = {i: self.cfg.init_balance for i in range(self.cfg.n_nodes)}
        nonce = {i: 0 for i in range(self.cfg.n_nodes)}
        for h in range(1, self.final_height + 1):
            bh = self.final_block_by_h[h]
            blk = self.blocks[bh]
            for tx in blk.txs:
                if tx.nonce != nonce[tx.frm]:
                    raise RuntimeError(f"Double-spend/nonce conflict: node {tx.frm} nonce {tx.nonce} expected {nonce[tx.frm]}")
                if bal[tx.frm] < tx.amount:
                    raise RuntimeError(f"Negative balance in final chain: node {tx.frm}")
                bal[tx.frm] -= tx.amount
                bal[tx.to] += tx.amount
                nonce[tx.frm] += 1

    def schedule_tick(self, now_ms: int):
        self.net.evt.push(now_ms + 100, "tick", {"node": self.id})

    def on_tick(self, now_ms: int):
        rate = self.cfg.tx_rate_per_node_per_sec
        r = H_int(self.cfg.seed.encode(), b"tick", bytes([self.id]), now_ms.to_bytes(8, "big"))
        p_num = int(rate * (2**256) / 10.0)
        if r < p_num:
            to = (self.id + 1 + (r % (self.cfg.n_nodes - 1))) % self.cfg.n_nodes
            amount = 1 + (r % 5)
            n = self.nonce[self.id]
            tid = H_hex(self.cfg.seed.encode(), b"tx", bytes([self.id]), now_ms.to_bytes(8, "big"))
            tx = Tx(frm=self.id, to=to, amount=amount, nonce=n, tid=tid)
            self.mempool.append(tx)
            self.nonce[self.id] += 1
            self.emit("tx_new", tid=tid, to=to, amount=amount, nonce=n)
        self.schedule_tick(now_ms)

    def schedule_work(self, now_ms: int):
        self.net.evt.push(now_ms + 1, "work", {"node": self.id})

    def leader_for_height(self, height: int, slot: int) -> int:
        total = sum(self.stake.values())
        if total <= 0:
            return 0
        r = H_int(self.cfg.seed.encode(), b"leader", height.to_bytes(8, "big"), slot.to_bytes(4, "big"))
        pick = r % total
        acc = 0
        for nid in range(self.cfg.n_nodes):
            acc += self.stake[nid]
            if pick < acc:
                return nid
        return self.cfg.n_nodes - 1

    def make_block_candidate(self, algo: str, height: int):
        parent = self.best_head
        txs: List[Tx] = []
        bal = self.balance.copy()
        nce = self.nonce.copy()
        for tx in list(self.mempool):
            if tx.frm == self.id and tx.nonce != nce[self.id]:
                continue
            if bal[tx.frm] >= tx.amount:
                bal[tx.frm] -= tx.amount
                bal[tx.to] += tx.amount
                nce[tx.frm] += 1
                txs.append(tx)
            if len(txs) >= 5:
                break
        header = f"{parent}|{height}|{self.id}|{algo}".encode()
        return header, txs, parent

    def try_hash(self, header: bytes, nonce: int, target_D: int):
        target = (1 << 256) // max(1, target_D)
        hval = int(H_hex(header, nonce.to_bytes(8, "big")), 16)
        ok = hval < target
        work = (1 << 32) // max(1, target_D)
        return ok, H_hex(header, nonce.to_bytes(8, "big")), work

    def on_work(self, now_ms: int):
        head_blk = self.blocks[self.best_head]
        height = head_blk.height + 1

        if self.cfg.algo == "pow":
            header, txs, parent = self.make_block_candidate("pow", height)
            attempts = 300
            base = self.pow_epoch * attempts + self.nonce_salt
            for i in range(attempts):
                nonce = base + i
                ok, bh, work = self.try_hash(header, nonce, self.cfg.pow_D)
                if ok:
                    blk = Block(
                        parent=parent, height=height, proposer=self.id, algo="pow",
                        difficulty=self.cfg.pow_D, stake_epoch=0, rnd_tag="", nonce=nonce,
                        txs=txs, bhash=bh, work=work
                    )
                    self.broadcast_block(blk, now_ms)
                    self.apply_local_block(blk)
                    break
            self.pow_epoch += 1

        elif self.cfg.algo == "hybrid":
            slot_len = 100
            slot = now_ms // slot_len
            leader = self.leader_for_height(height, slot)
            header, txs, parent = self.make_block_candidate("hybrid", height)
            attempts = 260 if self.id == leader else 12
            base = self.hybrid_epoch * attempts + self.nonce_salt
            for i in range(attempts):
                nonce = base + i
                ok, bh, work = self.try_hash(header, nonce, self.cfg.hybrid_D)
                if ok:
                    blk = Block(
                        parent=parent, height=height, proposer=self.id, algo="hybrid",
                        difficulty=self.cfg.hybrid_D, stake_epoch=slot, rnd_tag=f"s{slot}",
                        nonce=nonce, txs=txs, bhash=bh, work=work
                    )
                    self.broadcast_block(blk, now_ms)
                    self.apply_local_block(blk)
                    break
            self.hybrid_epoch += 1

        self.schedule_work(now_ms)

    def broadcast_block(self, blk: Block, now_ms: int):
        for dst in range(self.cfg.n_nodes):
            if dst == self.id:
                continue
            if not self.net.connected(self.id, dst, now_ms):
                continue
            ctx = bytes(blk.bhash, "utf-8")
            d = self.net.delay_ms(self.id, dst, ctx, now_ms)
            self.net.evt.push(now_ms + d, "recv_block", {
                "src": self.id, "dst": dst, "blk": self.block_to_dict(blk)
            })
        self.emit("block_mined" if self.cfg.algo == "pow" else "block_proposed",
                  height=blk.height, bhash=blk.bhash, leader=self.id)

    def apply_local_block(self, blk: Block):
        self.attach_block(blk)
        tids = {tx.tid for tx in blk.txs}
        if tids:
            self.mempool = [tx for tx in self.mempool if tx.tid not in tids]
        for tx in blk.txs:
            if self.balance[tx.frm] >= tx.amount:
                self.balance[tx.frm] -= tx.amount
                self.balance[tx.to] += tx.amount
        for tx in blk.txs:
            if self.nonce[tx.frm] <= tx.nonce:
                self.nonce[tx.frm] = tx.nonce + 1

    def on_recv_block(self, now_ms: int, blk_d: dict):
        blk = self.block_from_dict(blk_d)
        header = f"{blk.parent}|{blk.height}|{blk.proposer}|{blk.algo}".encode()
        target_D = self.cfg.pow_D if blk.algo == "pow" else self.cfg.hybrid_D if blk.algo == "hybrid" else 1
        ok, bh, _ = self.try_hash(header, blk.nonce, target_D)
        if not ok or bh != blk.bhash:
            return
        self.apply_local_block(blk)

    def block_to_dict(self, b: Block) -> dict:
        return {
            "parent": b.parent, "height": b.height, "proposer": b.proposer, "algo": b.algo,
            "difficulty": b.difficulty, "stake_epoch": b.stake_epoch, "rnd_tag": b.rnd_tag,
            "nonce": b.nonce, "txs": [tx.__dict__ for tx in b.txs], "bhash": b.bhash, "work": b.work
        }

    def block_from_dict(self, d: dict) -> Block:
        return Block(
            parent=d["parent"], height=d["height"], proposer=d["proposer"], algo=d["algo"],
            difficulty=d["difficulty"], stake_epoch=d["stake_epoch"], rnd_tag=d["rnd_tag"],
            nonce=d["nonce"], txs=[Tx(**t) for t in d["txs"]], bhash=d["bhash"], work=d["work"]
        )