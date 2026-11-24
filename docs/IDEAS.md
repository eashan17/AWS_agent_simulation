# Ideas (not in scope yet)

Anything outside the current slice goes here, one line each. Picked up only after the freeze is lifted or a slice is added by /build-plan.

- Bake-off: retest gpt-oss-120b with a larger `maxTokens` on the tiny smoke call; its reply was cut off at 50 tokens (`{"`), so the day-0 result is not a fair test.
- Slice 8 gotcha (found in slice 5): `queue_over_capacity` and `exception_queue_processed` link to every held request, so following *all* `caused_by` links from one student's eligibility also reaches other students' events. The detector should follow the student's own path (as `path()` in tests/test_chain.py does), not every ancestor.
- Hero hit rate (found in slice 6b, 0 of 9 real runs): a disruption lasts one class, so students lose 1–2 of 16 classes and stay far above 80%. A `duration_weeks` (or sessions) field on a disruption in the blueprint would let a strike or storm span several classes. Changes the Blueprint schema (slice 3a) and the term loop (slice 5): needs a team decision.
- Agents often ask for an exception before the class has happened (refused, correctly). Worth showing in the UI as a real finding about the policy's wording ("requests only after the absence is recorded").
