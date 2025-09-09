from models import Event
from utils import H_int

class EventLoop:
    def __init__(self):
        self.q = []
        self.eid = 0

    def push(self, t_ms, kind, data):
        self.eid += 1
        self.q.append(Event(t_ms, self.eid, kind, data))
        self.q.sort()

    def pop(self):
        return self.q.pop(0) if self.q else None

    def empty(self):
        return not self.q

class Network:
    def __init__(self, cfg):
        self.cfg = cfg
        self.evt = EventLoop()
        self.time_ms = 0

    def in_partition_window(self, t_ms):
        return self.cfg.partition_start_ms is not None and self.cfg.partition_start_ms <= t_ms < self.cfg.partition_end_ms

    def connected(self, src, dst, t_ms):
        if not self.in_partition_window(t_ms):
            return True
        if not self.cfg.partition_groups:
            return True
        for g in self.cfg.partition_groups:
            if src in g and dst in g:
                return True
        return False

    def delay_ms(self, src, dst, context, now_ms):
        base = self.cfg.base_delay_ms
        jitter = self.cfg.jitter_ms
        r = H_int(self.cfg.seed.encode(), b"delay", bytes([src, dst]), context, now_ms.to_bytes(8, "big"))
        return base + (r % (jitter + 1))
