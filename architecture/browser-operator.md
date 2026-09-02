# Browser Operator

The Browser Operator is an injectable Observe–Decide–Act–Verify–Recover machine. Its
adapter exposes only sanitized semantic observations, actions, verification, screenshot
capture, and screenshot deletion; it has no browser, network, credential, or commerce
implementation.

* DOM/SOM references from an observation are invalidated after every mutation.
* Confidence below the configured threshold produces `NEED_INPUT` without acting.
* An unverifiable delivery receives at most one equivalent retry; repeated state
  fingerprints produce `NEED_INPUT` rather than a no-op loop.
* Critical actions and semantic/visual conflicts require the injected independent Sol
  review callback. Sol is requested at medium effort by the change pipeline.
* Screenshots are temporary evidence and are deleted in success, failure, cancellation,
  and crash recovery paths. Persistent evidence is structured, fingerprinted, and
  redacted logs only.

Fixtures use a fake adapter and never contact a real browser or storefront.
