import argparse
from config import Config
from logger import FileLogger
from network import Network
from node import Node

def run(cfg: Config):
    logger = FileLogger(cfg.log_file)
    net = Network(cfg)
    nodes = [Node(i, cfg, net, logger) for i in range(cfg.n_nodes)]

    try:
        while not net.evt.empty():
            ev = net.evt.pop()
            net.time_ms = ev.t_ms
            if net.time_ms > cfg.sim_time_limit_ms:
                break
            if ev.kind == "tick":
                nodes[ev.data["node"]].on_tick(net.time_ms)
            elif ev.kind == "work":
                nodes[ev.data["node"]].on_work(net.time_ms)
            elif ev.kind == "recv_block":
                src = ev.data["src"]
                dst = ev.data["dst"]
                if net.connected(src, dst, net.time_ms):
                    nodes[dst].on_recv_block(net.time_ms, ev.data["blk"])
    except Exception as e:
        logger({"t": net.time_ms, "type": "error", "error": str(e)})
        logger.close()
        raise

    for n in nodes:
        head = n.blocks[n.best_head]
        logger({
            "summary": True,
            "node": n.id,
            "algo": cfg.algo,
            "best_height": head.height,
            "final_height": n.final_height,
            "best_head": n.best_head
        })

    logger.close()

def parse_args() -> Config:
    p = argparse.ArgumentParser()
    p.add_argument("--algo", choices=["pow", "hybrid"], default="pow")
    p.add_argument("--seed", type=str, default="seed-0")
    p.add_argument("--k", type=int, default=4)
    p.add_argument("--limit_ms", type=int, default=12000)
    p.add_argument("--delay", action="store_true")
    p.add_argument("--partition", action="store_true")
    p.add_argument("--log", type=str, default="log.jsonl")
    args = p.parse_args()

    cfg = Config()
    cfg.algo = args.algo
    cfg.seed = args.seed
    cfg.k_final = args.k
    cfg.sim_time_limit_ms = args.limit_ms
    cfg.log_file = args.log

    if args.delay:
        cfg.base_delay_ms = 60
        cfg.jitter_ms = 80

    if args.partition:
        cfg.partition_start_ms = 3000
        cfg.partition_end_ms = 6000
        cfg.partition_groups = [[0, 1, 2], [3, 4]]

    return cfg

if __name__ == "__main__":
    cfg = parse_args()
    run(cfg)
