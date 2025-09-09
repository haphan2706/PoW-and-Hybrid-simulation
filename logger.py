import json

class FileLogger:
    def __init__(self, filename: str):
        self.f = open(filename, "w", encoding="utf-8")

    def __call__(self, record: dict):
        self.f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def close(self):
        self.f.flush()
        self.f.close()
