"""Default hooks of a site with no parser of its own."""


def pop_host(host):
    return host


def binary_units(raw):
    """None: this site has no binary framing of its own; observe_drive falls back to MQTT, then one opaque unit."""
    return None


def expand_fields(path, value, event):
    """None: this site has no field to expand. A site that does returns the extra (path, value) pairs for the leaf
    (path, value) of the dict `event`, or [] when it tried and could not."""
    return None
