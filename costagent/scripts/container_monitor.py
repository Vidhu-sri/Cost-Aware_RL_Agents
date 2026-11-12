"""RSS samples tolerate process exit races, but never hide access failures."""
import os
import time
import psutil


def namespace_rss(pid, processes=psutil.process_iter, readlink=os.readlink):
    namespace = readlink(f'/proc/{pid}/ns/pid')
    rss = count = vanished = 0
    for candidate in processes(['pid']):
        try:
            if readlink(f'/proc/{candidate.pid}/ns/pid') != namespace:
                continue
        except (FileNotFoundError, ProcessLookupError, psutil.NoSuchProcess):
            continue
        except PermissionError:
            # Other users' namespaces may be unreadable; these are not members.
            continue
        try:
            value = candidate.memory_info().rss
        except (psutil.NoSuchProcess, psutil.ZombieProcess, FileNotFoundError, ProcessLookupError):
            vanished += 1
            continue
        # AccessDenied for a known member must be surfaced, not undercounted.
        rss += value
        count += 1
    if readlink(f'/proc/{pid}/ns/pid') != namespace:
        raise RuntimeError('Container namespace changed during sampling')
    if not count:
        raise RuntimeError('No readable live processes in container namespace')
    return {'observed_pid_namespace_rss_bytes': rss,
            'pid_namespace_processes': count, 'vanished_during_sample': vanished}


class SamplingHealth:
    def __init__(self, grace_seconds=5, clock=time.monotonic):
        self.grace_seconds = grace_seconds
        self.clock = clock
        self.failures = {}

    def success(self, identity):
        self.failures.pop(identity, None)

    def failure(self, identity, error):
        now = self.clock()
        since = self.failures.setdefault(identity, now)
        if now - since >= self.grace_seconds:
            raise RuntimeError(f'Monitor unavailable for {identity} for {now-since:.1f}s: {error}')
        return {'monitor_error': f'{type(error).__name__}: {error}',
                'monitor_gap_seconds': now-since}
