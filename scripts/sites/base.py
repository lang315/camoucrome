"""Default hooks of a site with no parser of its own."""


def pop_host(host):
    return host


def binary_units(raw):
    """None: this site has no binary framing of its own; observe_drive falls back to MQTT, then one opaque unit."""
    return None
