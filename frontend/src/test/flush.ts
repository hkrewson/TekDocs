/**
 * Let deferred work finish before a test ends.
 *
 * React roots that unmount during cleanup, and components that defer teardown to a
 * macrotask to avoid unmounting mid-render, both leave a callback queued after the
 * last assertion. Whether that callback runs before the suite finishes is a race, so
 * the lines inside it are covered on some runs and not others — which makes coverage
 * totals move on unchanged code and puts a threshold gate at the mercy of timing.
 *
 * Awaiting a zero-delay timer queues a macrotask behind the ones already pending, so
 * by the time this resolves, that deferred work has run.
 */
export async function flushDeferredWork(): Promise<void> {
  await new Promise((resolve) => {
    setTimeout(resolve, 0)
  })
}
