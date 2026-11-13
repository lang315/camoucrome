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
