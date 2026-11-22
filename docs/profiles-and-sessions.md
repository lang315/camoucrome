# Keeping a login alive across launches and updates

A logged-in identity is a browser profile, its fingerprint, and the cookies a site keeps rotating. If one of
them goes back to an old state or changes all at once, a site can re-check the device or end the session.

## What to do

- **Use one persistent profile per identity.** Launch the same `user_data_dir` every time, as the
  [Quickstart](../README.md#quickstart-two-identities) does. Do not restore a profile from an older copy. A
  site replaces its session cookies as you use it. A restored copy discards those and sends the old ones again.
- **Keep the fingerprint of a profile fixed.** Pass the same `seed` to `generate` on every launch, and pass
  `profile_seeds(user_data_dir)`, which reads the canvas, audio and media-device seeds stored in the profile.
  Keep the same proxy region, time zone and locale for that profile.
- **Expect one check after a camoucrome update.** A release on a newer Chrome version changes the user agent and
  client hints of every profile at once. A site may then re-check the device, or end an older session once. Open
  the profile as usual and log in again by hand if asked. Do not go back to a copy made before the update.

## Go core: store one identity, resolve it every launch

`core.Draw` returns a `core.Identity`. Store its JSON once per identity, next to the profile. It holds the full
pool entry, so a later release's data cannot change it.

- **On every launch**, call `Resolve(id, ProbeHost(), exit)` and launch with the result.
- **These fields must stay byte-stable:** `version`, `os`, `entry`, `seeds`, and `hostSeed` (a string, to keep 64
  bits). Never re-serialize the file through a type that rounds numbers.
- **These change per launch**, from the host and the exit: the core count snaps to the host, `platformVersion`,
  the window fit, and the time zone and locale.
- **Migration rule:** `Resolve` refuses a `version` this code does not read, and returns an error. Keep the file.
  Do not draw a new identity silently: a site that knew the old one sees a different device.
- **Keep one `user_data_dir` per identity.** Never start a fresh profile for an identity that has already logged in
  to a site account.
- **Moving an identity** to another host or another proxy country changes what a site sees. `Resolve` can drop the
  GPU claim (the host's cores fall below the claimed iGPU's floor, the CPU vendor does not fit, or the host GPU has
  another Dawn architecture), and the time zone changes. `Resolved.Warnings` names each such change: log every line.
  If the host's renderer is unknown (`""`), the architecture is not checked and the claim stays.

## What was measured

The tracking observer (`docs/observer/README.md`) loads facebook unattended. Each run copies a backed-up
logged-in profile into a fresh profile and deletes the copy afterwards. So every run sends the backup's cookies
again, which is the "restored copy" case above.

- A backup made on 2026-10-17 on the 156 build stayed logged in through runs up to 2026-11-12.
- On 2026-11-12 it was opened for the first time with the 157 build. In that logged-in load, facebook ran the
  device-fingerprint reads it otherwise runs only on its logged-out page: audio, canvas (381 calls), WebGL and
  WebGPU. The next run, 17 minutes later, found the session expired.
- After a fresh login by hand on the 157 build, two runs (the second about 4 hours after the login) stayed
  logged in. Neither ran those fingerprint reads, and canvas was called twice, as on 156.

This is one expired session. It does not separate the version change from the restored copy as the cause. It
is consistent with both acting together. Whether a fresh login survives 24 hours of restored copies is not
measured yet.
