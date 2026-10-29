/** Run the authoritative backend stop and local/WHIP cleanup independently. */
export async function stopSessionAndCleanup(stopSession, cleanupCapture = async () => null) {
  const [stopResult, cleanupResult] = await Promise.allSettled([
    Promise.resolve().then(stopSession),
    Promise.resolve().then(cleanupCapture)
  ]);

  const cleanupError = cleanupResult.status === 'rejected'
    ? cleanupResult.reason
    : cleanupResult.value?.cleanupError || null;

  if (stopResult.status === 'rejected') {
    const error = stopResult.reason instanceof Error ? stopResult.reason : new Error('The backend did not confirm the stream stop request.');
    if (cleanupError) error.cleanupError = cleanupError;
    throw error;
  }

  return { session: stopResult.value, cleanupError };
}
