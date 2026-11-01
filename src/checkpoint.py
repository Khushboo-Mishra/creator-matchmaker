"""Local, atomic completed-step cache. Never caches a failed call."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def atomic_write(path, value):
    temp = path.with_name(path.name + "." + str(uuid4()) + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


class Checkpoint:
    def __init__(self, directory, bindings, at, resume=False):
        self.directory = Path(directory)
        manifest = self.directory / "checkpoint.json"
        if resume:
            state = json.loads(manifest.read_text(encoding="utf-8"))
            checksum = state.pop("checksum")
            if digest(state) != checksum:
                raise ValueError("Checkpoint manifest integrity mismatch")
            if state["bindings"] != bindings:
                raise ValueError(
                    "Checkpoint inputs, code, model or settings changed; cannot resume"
                )
            self.at = state["at"]
        else:
            self.directory.mkdir(parents=True, exist_ok=False)
            state = {"bindings": bindings, "at": at.isoformat()}
            atomic_write(manifest, dict(state, checksum=digest(state)))
            self.at = state["at"]

    def call(self, stage, inputs, fn):
        key = digest({"stage": stage, "inputs": inputs})
        path = self.directory / (stage + "-" + key + ".json")
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["key"] != key or digest(record["value"]) != record["checksum"]:
                raise ValueError(f"Checkpoint integrity mismatch for {stage}")
            return deepcopy(record["value"])
        value = fn()
        atomic_write(path, {"key": key, "value": value, "checksum": digest(value)})
        return value


class CachedProvider:
    def __init__(self, provider, checkpoint):
        self.provider = provider
        self.checkpoint = checkpoint
        self.mode = provider.mode
        self.model = provider.model

    @property
    def last_response_text(self):
        return getattr(self.provider, "last_response_text", None)

    @last_response_text.setter
    def last_response_text(self, value):
        self.provider.last_response_text = value

    @property
    def last_judgment(self):
        return getattr(self.provider, "last_judgment", None)

    @last_judgment.setter
    def last_judgment(self, value):
        self.provider.last_judgment = value

    def discover(self, campaign):
        return self.checkpoint.call(
            "discovery", campaign.canonical(), lambda: self.provider.discover(campaign)
        )

    def channel(self, candidate):
        return self.checkpoint.call(
            "channel", candidate, lambda: self.provider.channel(candidate)
        )

    def comments(self, channel):
        return self.checkpoint.call(
            "comments", channel, lambda: self.provider.comments(channel)
        )

    def embed(self, text):
        return self.checkpoint.call(
            "embedding", text, lambda: self.provider.embed(text)
        )

    def judge(self, *args):
        return self.provider.judge(*args)
