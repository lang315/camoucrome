"""C4 of verify_sp6b_driver: the browser argv against launcher.json's expected set, without a browser."""


def argv_diff(got, expected, self_added):
    """(unexpected, absent) for a set of browser args. The driver's args (`expected`) must all be present and nothing
    outside `expected | self_added` may appear. `self_added` is Chrome's own headless additions: they are allowed but not
    required, because /proc shows them only when the browser rewrites its process title (see verify_sp6b_driver)."""
    got, expected, self_added = set(got), set(expected), set(self_added)
    return sorted(got - expected - self_added), sorted(expected - got)
