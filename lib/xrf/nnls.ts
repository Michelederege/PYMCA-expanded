/**
 * Non-negative least squares via an active set on the normal equations.
 * Columns are the peak shapes, y is net counts. invVar is 1/variance per channel.
 */
export function nnls(
  columns: Float64Array[],
  y: Float64Array,
  invVar: Float64Array,
): Float64Array {
  const n = columns.length;
  const m = y.length;
  const x = new Float64Array(n);
  if (n === 0 || m === 0) return x;

  const ata = Array.from({ length: n }, () => new Float64Array(n));
  const atb = new Float64Array(n);
  for (let j = 0; j < n; j++) {
    const colJ = columns[j];
    let bj = 0;
    for (let i = 0; i < m; i++) bj += invVar[i] * colJ[i] * y[i];
    atb[j] = bj;
    for (let k = j; k < n; k++) {
      const colK = columns[k];
      let dot = 0;
      for (let i = 0; i < m; i++) dot += invVar[i] * colJ[i] * colK[i];
      ata[j][k] = dot;
      ata[k][j] = dot;
    }
  }

  const active = Array(n).fill(true);
  const gradScale = atb.reduce((sum, value) => sum + Math.abs(value), 0) + 1;

  for (let iter = 0; iter < n + 3; iter++) {
    const idx: number[] = [];
    for (let j = 0; j < n; j++) if (active[j]) idx.push(j);
    if (idx.length === 0) break;

    const matrix = idx.map((row) => idx.map((col) => ata[row][col]));
    const rhs = idx.map((row) => atb[row]);
    for (let i = 0; i < matrix.length; i++) {
      matrix[i][i] += 1e-8 * (Math.abs(matrix[i][i]) + 1);
    }
    const solution = solveLinear(matrix, rhs);

    let dropped = false;
    for (let t = 0; t < idx.length; t++) {
      if (!(solution[t] > 0)) {
        active[idx[t]] = false;
        x[idx[t]] = 0;
        dropped = true;
      }
    }
    if (dropped) continue;

    for (let t = 0; t < idx.length; t++) x[idx[t]] = solution[t];

    let enter = -1;
    let best = 0;
    for (let j = 0; j < n; j++) {
      if (active[j]) continue;
      let gradient = atb[j];
      for (const k of idx) gradient -= ata[j][k] * x[k];
      if (gradient > best) {
        best = gradient;
        enter = j;
      }
    }
    if (enter >= 0 && best > 1e-7 * gradScale) {
      active[enter] = true;
      continue;
    }
    for (let j = 0; j < n; j++) if (!active[j]) x[j] = 0;
    return x;
  }

  for (let j = 0; j < n; j++) if (!active[j]) x[j] = 0;
  return x;
}

export function solveLinear(a: number[][], b: number[]): number[] {
  const n = b.length;
  const m = a.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let row = col + 1; row < n; row++) {
      if (Math.abs(m[row][col]) > Math.abs(m[pivot][col])) pivot = row;
    }
    if (Math.abs(m[pivot][col]) < 1e-14) {
      for (let c = 0; c <= n; c++) m[col][c] = 0;
      m[col][col] = 1;
      continue;
    }
    if (pivot !== col) {
      const swap = m[col];
      m[col] = m[pivot];
      m[pivot] = swap;
    }
    const div = m[col][col];
    for (let c = col; c <= n; c++) m[col][c] /= div;
    for (let row = 0; row < n; row++) {
      if (row === col) continue;
      const factor = m[row][col];
      if (factor === 0) continue;
      for (let c = col; c <= n; c++) m[row][c] -= factor * m[col][c];
    }
  }
  return m.map((row) => row[n]);
}
