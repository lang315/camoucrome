# Acceptable use

Camoucrome is a Chromium build that presents a configured browser fingerprint
instead of the machine's own. It exists for people who run many browser
identities on their own machines for legitimate reasons. Typical uses:

- **Privacy.** Keeping websites from linking your sessions together by your
  device.
- **Testing and quality assurance.** Exercising a site the way browsers on
  other devices, locales and screens see it.
- **Research.** Measuring how fingerprinting and bot detection behave, including
  on your own systems.
- **Account separation.** Operating several accounts that you are entitled to
  operate, where the service allows it.

## Not acceptable

Do not use Camoucrome, or anything built from it, to:

- commit fraud, including payment, advertising, promotion and account-creation
  fraud;
- get into accounts or systems you are not authorised to access, including
  credential stuffing and account takeover;
- impersonate a real person or organisation in order to deceive;
- evade a ban or block that was imposed to stop harassment, abuse or fraud;
- harass, stalk or surveil people;
- distribute malware or run attacks against systems you do not own or have
  written permission to test;
- break the law where you or the target are.

The licence (MPL-2.0, see `LICENSE`) governs copying and modification. This
statement says what the maintainers build the project for and will not help
with. A request for help with a use listed above will be declined, as will an
issue or pull request whose purpose is one of those uses.

## Your responsibility

You are responsible for complying with the laws that apply to you and with the
terms of the services you use. Many websites forbid automated access or
multiple accounts; this software does not change what you have agreed to.

The project is provided as is, without warranty of any kind (sections 6 and 7
of the licence). A spoofed fingerprint is not anonymity. Your IP address, your
account and your behaviour identify you whatever the browser reports.

## Codecs and patents

Released binaries include the H.264 and AAC codecs that stock Chrome ships,
because leaving them out is itself a detectable difference. Google's licence
for those codecs covers Google's builds, not this one. Patent obligations for
distributing and using them may apply in your jurisdiction, and you accept that
risk by using a released binary. The source can be built without them
(`proprietary_codecs = false`), at the cost of that detectable difference.
