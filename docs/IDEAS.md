# Ideas (not in scope yet)

Anything outside the current slice goes here, one line each. Picked up only after the freeze is lifted or a slice is added by /build-plan.

- Bake-off: retest gpt-oss-120b with a larger `maxTokens` on the tiny smoke call; its reply was cut off at 50 tokens (`{"`), so the day-0 result is not a fair test.
- Slice 8 gotcha (found in slice 5): `queue_over_capacity` and `exception_queue_processed` link to every held request, so following *all* `caused_by` links from one student's eligibility also reaches other students' events. The detector should follow the student's own path (as `path()` in tests/test_chain.py does), not every ancestor.
