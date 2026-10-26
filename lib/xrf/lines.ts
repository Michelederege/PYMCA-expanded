export type Series = "Ka" | "Kb" | "La" | "Lb" | "Lg";

export type XrayLine = {
  symbol: string;
  z: number;
  series: Series;
  /** Intensity-weighted emission energy, keV. */
  energy: number;
  /** Absorption edge that must be exceeded to excite this line, keV. */
  edge: number;
};

type RawElement = {
  symbol: string;
  z: number;
  ka1: number;
  ka2: number;
  kb: number;
  kEdge: number;
  la?: number;
  lb?: number;
  lg?: number;
  l3?: number;
  l2?: number;
  l1?: number;
};

const ELEMENTS: RawElement[] = [
  { symbol: "Na", z: 11, ka1: 1.04098, ka2: 1.04098, kb: 1.0711, kEdge: 1.0708 },
  { symbol: "Mg", z: 12, ka1: 1.2536, ka2: 1.2536, kb: 1.3022, kEdge: 1.305 },
  { symbol: "Al", z: 13, ka1: 1.4867, ka2: 1.4863, kb: 1.5574, kEdge: 1.5596 },
  { symbol: "Si", z: 14, ka1: 1.73998, ka2: 1.73938, kb: 1.8359, kEdge: 1.8389 },
  { symbol: "P", z: 15, ka1: 2.0137, ka2: 2.0127, kb: 2.1391, kEdge: 2.1455 },
  { symbol: "S", z: 16, ka1: 2.30784, ka2: 2.30664, kb: 2.464, kEdge: 2.472 },
  { symbol: "Cl", z: 17, ka1: 2.62239, ka2: 2.62078, kb: 2.8156, kEdge: 2.8224 },
  { symbol: "K", z: 19, ka1: 3.3138, ka2: 3.3111, kb: 3.5896, kEdge: 3.6074 },
  { symbol: "Ca", z: 20, ka1: 3.69168, ka2: 3.68809, kb: 4.0127, kEdge: 4.0385 },
  { symbol: "Sc", z: 21, ka1: 4.0906, ka2: 4.0861, kb: 4.4605, kEdge: 4.4928 },
  { symbol: "Ti", z: 22, ka1: 4.51084, ka2: 4.50486, kb: 4.93181, kEdge: 4.9664 },
  { symbol: "V", z: 23, ka1: 4.9522, ka2: 4.94464, kb: 5.42729, kEdge: 5.4651 },
  { symbol: "Cr", z: 24, ka1: 5.41472, ka2: 5.40551, kb: 5.94671, kEdge: 5.9892 },
  { symbol: "Mn", z: 25, ka1: 5.89875, ka2: 5.88765, kb: 6.49045, kEdge: 6.539 },
  { symbol: "Fe", z: 26, ka1: 6.40384, ka2: 6.39084, kb: 7.05798, kEdge: 7.112 },
  { symbol: "Co", z: 27, ka1: 6.93032, ka2: 6.9153, kb: 7.64943, kEdge: 7.7089 },
  { symbol: "Ni", z: 28, ka1: 7.47815, ka2: 7.46089, kb: 8.26466, kEdge: 8.3328 },
  { symbol: "Cu", z: 29, ka1: 8.04778, ka2: 8.02783, kb: 8.90529, kEdge: 8.9789 },
  { symbol: "Zn", z: 30, ka1: 8.63886, ka2: 8.61578, kb: 9.572, kEdge: 9.6586 },
  { symbol: "Ga", z: 31, ka1: 9.25174, ka2: 9.22482, kb: 10.2642, kEdge: 10.3671 },
  { symbol: "Ge", z: 32, ka1: 9.88642, ka2: 9.85532, kb: 10.9821, kEdge: 11.1031 },
  { symbol: "As", z: 33, ka1: 10.54372, ka2: 10.50799, kb: 11.7262, kEdge: 11.867 },
  { symbol: "Se", z: 34, ka1: 11.2224, ka2: 11.1814, kb: 12.4959, kEdge: 12.6578 },
  { symbol: "Br", z: 35, ka1: 11.9242, ka2: 11.8776, kb: 13.2914, kEdge: 13.4737 },
  { symbol: "Rb", z: 37, ka1: 13.3953, ka2: 13.3358, kb: 14.9613, kEdge: 15.1997 },
  { symbol: "Sr", z: 38, ka1: 14.165, ka2: 14.0979, kb: 15.8357, kEdge: 16.1046 },
  { symbol: "Y", z: 39, ka1: 14.9584, ka2: 14.8829, kb: 16.7378, kEdge: 17.0384 },
  { symbol: "Zr", z: 40, ka1: 15.7751, ka2: 15.6909, kb: 17.6678, kEdge: 17.9976 },
  { symbol: "Nb", z: 41, ka1: 16.6151, ka2: 16.521, kb: 18.6225, kEdge: 18.9856 },
  { symbol: "Mo", z: 42, ka1: 17.47934, ka2: 17.3743, kb: 19.6083, kEdge: 19.9995 },
  { symbol: "Ag", z: 47, ka1: 22.16292, ka2: 21.9903, kb: 24.9424, kEdge: 25.514 },
  { symbol: "Cd", z: 48, ka1: 23.1736, ka2: 22.9841, kb: 26.0955, kEdge: 26.7112 },
  { symbol: "Sn", z: 50, ka1: 25.2713, ka2: 25.044, kb: 28.486, kEdge: 29.2001 },
  { symbol: "Ba", z: 56, ka1: 32.1936, ka2: 31.8171, kb: 36.3782, kEdge: 37.4406 },
  {
    symbol: "W",
    z: 74,
    ka1: 59.3182,
    ka2: 57.9817,
    kb: 67.2443,
    kEdge: 69.525,
    la: 8.3976,
    lb: 9.67235,
    lg: 11.2859,
    l3: 10.2068,
    l2: 11.544,
    l1: 12.0998,
  },
  {
    symbol: "Au",
    z: 79,
    ka1: 68.8037,
    ka2: 66.9895,
    kb: 77.984,
    kEdge: 80.7249,
    la: 9.7133,
    lb: 11.4423,
    lg: 13.3817,
    l3: 11.9187,
    l2: 13.7336,
    l1: 14.353,
  },
  {
    symbol: "Hg",
    z: 80,
    ka1: 70.819,
    ka2: 68.895,
    kb: 80.253,
    kEdge: 83.102,
    la: 9.9888,
    lb: 11.8226,
    lg: 13.83,
    l3: 12.2839,
    l2: 14.2089,
    l1: 14.8393,
  },
  {
    symbol: "Pb",
    z: 82,
    ka1: 74.9694,
    ka2: 72.8042,
    kb: 84.936,
    kEdge: 88.0045,
    la: 10.5515,
    lb: 12.6137,
    lg: 14.7644,
    l3: 13.0352,
    l2: 15.200,
    l1: 15.8608,
  },
  {
    symbol: "Bi",
    z: 83,
    ka1: 77.1079,
    ka2: 74.8148,
    kb: 87.343,
    kEdge: 90.5259,
    la: 10.8388,
    lb: 13.0235,
    lg: 15.2477,
    l3: 13.4186,
    l2: 15.7111,
    l1: 16.3875,
  },
  {
    symbol: "U",
    z: 92,
    ka1: 98.439,
    ka2: 94.665,
    kb: 111.3,
    kEdge: 115.606,
    la: 13.6147,
    lb: 17.22,
    lg: 20.1671,
    l3: 17.1663,
    l2: 20.9476,
    l1: 21.7574,
  },
];

function blendKa(ka1: number, ka2: number): number {
  return (2 * ka1 + ka2) / 3;
}

function pushLine(
  lines: XrayLine[],
  element: RawElement,
  series: Series,
  energy: number,
  edge: number,
) {
  lines.push({
    symbol: element.symbol,
    z: element.z,
    series,
    energy,
    edge,
  });
}

export const LINES: XrayLine[] = ELEMENTS.flatMap((element) => {
  const lines: XrayLine[] = [];
  pushLine(lines, element, "Ka", blendKa(element.ka1, element.ka2), element.kEdge);
  pushLine(lines, element, "Kb", element.kb, element.kEdge);
  if (element.la && element.l3) pushLine(lines, element, "La", element.la, element.l3);
  if (element.lb && element.l2) pushLine(lines, element, "Lb", element.lb, element.l2);
  if (element.lg && element.l1) pushLine(lines, element, "Lg", element.lg, element.l1);
  return lines;
});

export function lineKey(line: Pick<XrayLine, "symbol" | "series">): string {
  return `${line.symbol} ${line.series}`;
}

export function findLine(key: string): XrayLine | undefined {
  return LINES.find((line) => lineKey(line) === key);
}

export function elementOf(key: string): string {
  return key.split(" ")[0] ?? key;
}

export const SYMBOLS = [...new Set(LINES.map((line) => line.symbol))];
