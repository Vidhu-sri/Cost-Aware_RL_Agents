"""Request-level RFT -> DPO -> sticky SDPO, layered on PhaseRouter.
Heuristic policy, no learned gate and no correctness claim from test exit 0.
"""
import hashlib
import json
import re
import shlex
import time
from pathlib import Path
from phase_router import PhaseRouter

VERSION = 'method-v1-sticky'
MODELS = {'rft': 'rft_lora', 'dpo': 'dpo_lora', 'sdpo': 'sdpo_lora'}


def recognized_test(command):
    # Conservatively accept a single test command, optionally after cd DIR &&.
    # Never treat grep/echo mentioning pytest or a pipeline's exit as test success.
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        return False
    if len(words) > 3 and words[0] == 'cd' and words[2] == '&&':
        words = words[3:]
    if not words or any(x in command for x in ('|', ';', '\n', '`', '$(', '>', '<')):
        return False
    if any(x in {'&&', '&'} for x in words):
        return False
    first = Path(words[0]).name
    if first in {'pytest', 'py.test', 'tox'}:
        return True
    if re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', first):
        return len(words) >= 3 and words[1] == '-m' and words[2] in {'pytest', 'unittest'}
    return False


def object_value(value):
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


class MethodRouter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = None
        self.phase = PhaseRouter(clock=clock)
        self.method = 'rft'
        self.calls = {}
        self.seen = set()
        self.exchanges = []
        self.cache = {}
        self.switches = 0

    def start(self):
        if self.started is None:
            self.started = self.clock()
            self.phase.started = self.started

    def route(self, payload):
        if payload.get('model', '').removeprefix('openai/') not in {'main_lora', 'costlora'}:
            return payload, None
        self.start()
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if key in self.cache:
            body, record = self.cache[key]
            return body, dict(record, retry_same_request=True, time=time.time())
        for message in payload.get('messages', []):
            for call in message.get('tool_calls') or []:
                if call.get('id'):
                    self.calls[call['id']] = call.get('function', {})
            ident = message.get('tool_call_id')
            if message.get('role') != 'tool' or not ident or ident in self.seen or ident not in self.calls:
                continue
            self.seen.add(ident)
            fn = self.calls[ident]
            args = object_value(fn.get('arguments', {}))
            obs = object_value(message.get('content'))
            if fn.get('name') in {'get_status', 'submit_patch'}:
                continue
            stdout, stderr = obs.get('stdout'), obs.get('stderr')
            digest = None
            if isinstance(stdout, str) and isinstance(stderr, str):
                digest = hashlib.sha256(json.dumps([stdout, stderr], ensure_ascii=False).encode()).hexdigest()
            self.exchanges.append({'id': ident, 'name': fn.get('name'),
                                   'command': args.get('command'), 'output_sha256': digest,
                                   'exit_code': obs.get('exit_code')})
        elapsed = self.clock() - self.started
        last = self.exchanges[-1] if self.exchanges else {}
        prev = self.exchanges[-2] if len(self.exchanges) >= 2 else {}
        repeat = bool(last.get('name') == prev.get('name') == 'run_command'
                      and isinstance(last.get('command'), str)
                      and last.get('command') == prev.get('command')
                      and last.get('output_sha256') is not None
                      and last.get('output_sha256') == prev.get('output_sha256'))
        test_ok = (last.get('name') == 'run_command' and type(last.get('exit_code')) is int
                   and last['exit_code'] == 0 and recognized_test(last.get('command') or ''))
        triggers = {'budget_240s': elapsed >= 240, 'repeat': repeat, 'successful_test': test_ok}
        previous = self.method
        if self.method == 'sdpo':
            reason = 'sticky_sdpo'
        elif any(triggers.values()):
            self.method = 'sdpo'
            reason = next(k for k, value in triggers.items() if value)
        elif len(self.exchanges) >= 2:
            self.method, reason = 'dpo', 'two_completed_exchanges'
        else:
            reason = 'rft_initial_context'
        self.switches += previous != self.method
        body, phase_record = self.phase.route(payload)
        body['model'] = MODELS[self.method]
        record = {'version': VERSION, 'time': time.time(), 'elapsed_seconds': elapsed,
                  'method': self.method, 'model': body['model'], 'previous_method': previous,
                  'reason': reason, 'triggers': triggers, 'completed_exchanges': len(self.exchanges),
                  'switches': self.switches, 'last_exchange': last,
                  'request_sha256': key, 'phase_controller': phase_record}
        self.cache[key] = body, record
        return body, record


def install(out):
    import httpx
    out = Path(out)
    router = MethodRouter()
    original = httpx.AsyncClient.send

    async def send(client, request, *args, **kwargs):
        if (request.url.host == '127.0.0.1' and request.url.port == 8001
                and request.url.path.endswith('/chat/completions')):
            body, record = router.route(json.loads(request.content))
            if record is not None:
                headers = dict(request.headers)
                headers.pop('content-length', None)
                request = httpx.Request(request.method, request.url, headers=headers,
                                        content=json.dumps(body).encode(), extensions=request.extensions)
                with (out / 'router_decisions.jsonl').open('a') as f:
                    f.write(json.dumps(record) + '\n')
        return await original(client, request, *args, **kwargs)

    httpx.AsyncClient.send = send
    return router
