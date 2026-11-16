"""Stock's variations command line (chrome://version/?show-variations-cmd) as a feature list the harness can halve.

The text is per-client data (it can carry country, locale, consistency ids): keep it outside the repo. parse() keeps
only features, trials and params; a feature token stays verbatim (`*` default-kept prefix, `<Trial`, `:params`)."""
import re

_SWITCH = re.compile(r"--([a-z-]+)=(\S*)")


def parse(text):
    got = {k: v for k, v in _SWITCH.findall(text)}
    split = lambda k: [t for t in got.get(k, "").split(",") if t]
    return {"features": {"enable": split("enable-features"), "disable": split("disable-features")},
            "trials": got.get("force-fieldtrials", ""), "params": got.get("force-fieldtrial-params", "")}


def _name(token):
    return re.split(r"[<:]", token.lstrip("*"), maxsplit=1)[0]


def _pick(tokens, names):
    if names is None:
        return list(tokens)
    have = {_name(t) for t in tokens}
    missing = [n for n in names if n not in have]
    if missing:
        raise KeyError(missing[0])
    return [t for t in tokens if _name(t) in set(names)]


def subset(sw, enable=None, disable=None, keep_trials=True, keep_params=True):
    """The named features only (None keeps every one of that list), tokens in their original order."""
    return {"features": {"enable": _pick(sw["features"]["enable"], enable),
                         "disable": _pick(sw["features"]["disable"], disable)},
            "trials": sw["trials"] if keep_trials else "", "params": sw["params"] if keep_params else ""}


def argv(sw):
    pairs = [("force-fieldtrials", sw["trials"]), ("force-fieldtrial-params", sw["params"]),
             ("enable-features", ",".join(sw["features"]["enable"])),
             ("disable-features", ",".join(sw["features"]["disable"]))]
    return [f"--{k}={v}" for k, v in pairs if v]
