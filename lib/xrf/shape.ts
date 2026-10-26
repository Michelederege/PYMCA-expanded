/** Si detector constants used to turn one resolution number into a width at any energy. */
const FANO = 0.114;
const PAIR_EV = 3.64;
const GAUSS_FWHM = 2.354820045;

export function statisticalFwhmEv(energyKeV: number): number {
  const energyEv = Math.max(0, energyKeV) * 1000;
  return GAUSS_FWHM * Math.sqrt(FANO * PAIR_EV * energyEv);
}

export function fwhmEv(energyKeV: number, fwhmAtMnEv: number): number {
  const statMn = statisticalFwhmEv(5.89875);
  const noise2 = Math.max(40 ** 2, fwhmAtMnEv ** 2 - statMn ** 2);
  const stat = statisticalFwhmEv(energyKeV);
  return Math.sqrt(noise2 + stat * stat);
}

export function sigmaChannels(energyKeV: number, fwhmAtMnEv: number, gainKeV: number): number {
  const sigmaKeV = fwhmEv(energyKeV, fwhmAtMnEv) / 1000 / GAUSS_FWHM;
  return sigmaKeV / Math.abs(gainKeV);
}

/** Add a gaussian normalized so its channel sum is ~1, then scaled. */
export function addUnitGaussian(
  target: Float64Array,
  mu: number,
  sigma: number,
  scale: number,
): void {
  if (!(sigma > 0) || scale === 0 || !Number.isFinite(mu)) return;
  const lo = Math.max(0, Math.floor(mu - 6 * sigma));
  const hi = Math.min(target.length - 1, Math.ceil(mu + 6 * sigma));
  const inv = 1 / (sigma * Math.sqrt(2 * Math.PI));
  for (let i = lo; i <= hi; i++) {
    const d = (i - mu) / sigma;
    target[i] += scale * inv * Math.exp(-0.5 * d * d);
  }
}

export function channelOf(energyKeV: number, zero: number, gain: number): number {
  return (energyKeV - zero) / gain;
}

export function energyOf(channel: number, zero: number, gain: number): number {
  return zero + gain * channel;
}
