/**
 * SNIP background (Ryan 1988) in log-log-square space.
 * Iterations should be on the order of the peak width in channels.
 */
export function snipBackground(y: Float64Array, iterations: number): Float64Array {
  const n = y.length;
  const current = new Float64Array(n);
  for (let i = 0; i < n; i++) current[i] = forward(Math.max(0, y[i]));

  const passes = Math.max(0, Math.round(iterations));
  for (let p = 1; p <= passes; p++) {
    const next = current.slice();
    for (let i = p; i < n - p; i++) {
      const average = (current[i - p] + current[i + p]) / 2;
      if (average < next[i]) next[i] = average;
    }
    current.set(next);
  }

  const background = new Float64Array(n);
  for (let i = 0; i < n; i++) background[i] = Math.max(0, inverse(current[i]));
  return background;
}

function forward(y: number): number {
  return Math.log(Math.log(Math.sqrt(y + 1) + 1) + 1);
}

function inverse(v: number): number {
  const inner = Math.exp(v) - 1;
  const root = Math.exp(inner) - 1;
  return root * root - 1;
}
