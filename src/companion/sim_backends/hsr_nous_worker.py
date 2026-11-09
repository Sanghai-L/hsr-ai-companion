"""Standalone stdlib-only JSON bridge, executed by the optional core runtime.

Do not import companion here: the core environment deliberately has no main-app
dependencies. The only imported upstream modules belong to the locked core.
"""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import sys
import warnings


def offline_guard(event, args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.sendto", "socket.bind",
                 "subprocess.Popen", "os.system", "os.startfile"}:
        raise RuntimeError("offline simulation forbids " + event)


def main():
    request = json.loads(sys.stdin.buffer.read(1024 * 1024 + 1))
    if request.get("protocol") != 1 or request.get("operation") not in {"compile", "execute"}:
        raise ValueError("unsupported backend protocol")
    repository = Path(request["repository"])
    os.environ["HSR_NOUS_DATA_DIR"] = request["data"]
    sys.path.insert(0, str(repository / "src"))
    sys.addaudithook(offline_guard)
    from hsr_nous.sim.compile import compile_encounter
    from hsr_nous.sim import CombatEngine, MODE_ROLL, MODE_EXPECTED
    from hsr_nous.sim.structured_log import StructuredLogger
    value = request["input"]
    diagnostics = io.StringIO()
    with redirect_stdout(diagnostics), redirect_stderr(diagnostics), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compiled = compile_encounter(value["build"], value["stage"], template_roots=request["template_roots"])
        enemies = list(compiled.stage.enemies) + [actor for wave in compiled.stage.waves.values() for actor in wave]
        overrides = value.get("enemy_overrides", {})
        enemy_ids = {actor.actor_id for actor in enemies}
        if set(overrides) - enemy_ids:
            raise ValueError("enemy overrides contain actors outside the frozen stage")
        for actor in enemies:
            for key, number in overrides.get(actor.actor_id, {}).items():
                setattr(actor.stats, key, number)
        data = {"caveats": list(compiled.caveats),
                "compiled_enemies": [{"actor_id": actor.actor_id, "level": actor.level, "hp": actor.stats.hp,
                    "atk": actor.stats.atk, "def_": actor.stats.def_, "spd": actor.stats.spd,
                    "effect_res": actor.stats.effect_res, "max_toughness": actor.stats.max_toughness,
                    "resistance": dict(actor.stats.resistance)} for actor in enemies]}
        if request["operation"] == "execute":
            engine = CombatEngine.from_compiled(compiled, mode=MODE_ROLL if value["mode"] == "roll" else MODE_EXPECTED,
                                                seed=value["seed"], initial_sp=value["initial_sp"],
                                                initial_energy_ratio=value["initial_energy_ratio"])
            logger = StructuredLogger(engine)
            samples = []
            original = engine.pipeline.settle_damage

            def observe_damage(*args, **kwargs):
                result = original(*args, **kwargs)
                if len(samples) < 3:
                    samples.append(asdict(result))
                return result

            engine.pipeline.settle_damage = observe_damage
            state = engine.run()
            endings = [entry for entry in logger.entries if entry.get("event_type") == "battle_end"]
            data.update(snapshot=state.snapshot(), events=logger.entries, log=state.log, damage_samples=samples,
                        termination=endings[-1].get("reason", "unknown") if endings else "unknown", current_wave=engine.current_wave)
        data["warnings"] = list(dict.fromkeys(str(w.message) for w in caught))
        data["diagnostics"] = diagnostics.getvalue()[:8192]
    return {"protocol": 1, "status": "success", "data": data}


if __name__ == "__main__":
    try:
        response = main()
        exit_code = 0
    except Exception as error:
        response = {"protocol": 1, "status": "error", "error": {
            "code": "UNSUPPORTED" if isinstance(error, NotImplementedError) else "INVALID_INPUT" if isinstance(error, (ValueError, KeyError, TypeError)) else "INTERNAL_FAILURE",
            "type": type(error).__name__, "message": str(error)[:1500]}}
        exit_code = 1
    sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False))
    raise SystemExit(exit_code)
