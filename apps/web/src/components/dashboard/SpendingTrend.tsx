import { formatLedgerMonth, formatMoney } from '../../lib/ledger-formatters';
import { Card } from './Card';
import type {
  DashboardSpendingPoint,
  DashboardSpendingTrendData,
} from './types';

const chartWidth = 620;
const chartHeight = 150;
const horizontalInset = 10;

interface ChartPoint extends DashboardSpendingPoint {
  readonly label: string;
  readonly x: number;
  readonly y: number;
}

interface ChartGeometry {
  readonly baselineY: number;
  readonly points: readonly ChartPoint[];
}

function chartAmount(amount: string): number {
  const value = Number(amount);
  if (!amount.trim() || !Number.isFinite(value)) {
    throw new RangeError('Chart amounts must be finite decimal strings.');
  }
  return value;
}

function buildChartPoints(
  points: readonly DashboardSpendingPoint[],
): ChartGeometry {
  // Number conversion is used only for SVG geometry. Displayed values and all
  // ledger totals remain the exact decimal strings returned by the service.
  const amounts = points.map((point) => chartAmount(point.amount));
  const minimumAmount = Math.min(...amounts, 0);
  const maximumAmount = Math.max(...amounts, 0);
  const range = maximumAmount - minimumAmount;
  const verticalInset = 18;
  const scaleY = (amount: number) =>
    range === 0
      ? chartHeight / 2
      : verticalInset +
        ((maximumAmount - amount) / range) * (chartHeight - verticalInset * 2);

  return {
    baselineY: scaleY(0),
    points: points.map((point, index) => {
      const x =
        points.length === 1
          ? chartWidth / 2
          : horizontalInset +
            (index * (chartWidth - horizontalInset * 2)) / (points.length - 1);

      return {
        ...point,
        label: formatLedgerMonth(point.monthStart),
        x,
        y: scaleY(amounts[index]!),
      };
    }),
  };
}

export function SpendingTrend({
  comparisonLabel,
  currency,
  currentAmount,
  points,
  statusLabel,
}: DashboardSpendingTrendData) {
  const chart = buildChartPoints(points);
  const chartPoints = chart.points;
  const linePath = chartPoints
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ');
  const firstPoint = chartPoints[0];
  const lastPoint = chartPoints.at(-1);
  const areaPath =
    firstPoint && lastPoint
      ? `${linePath} L ${lastPoint.x} ${chart.baselineY} L ${firstPoint.x} ${chart.baselineY} Z`
      : '';

  return (
    <Card className="min-w-0 p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">Spending trend</p>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <p className="text-2xl font-semibold tracking-[-0.035em] text-slate-900">
              {formatMoney(currentAmount, currency)}
            </p>
          </div>
          <p className="mt-1 text-[11px] font-medium text-slate-600">
            {comparisonLabel}
          </p>
        </div>
        {statusLabel && (
          <span className="rounded-full bg-mist-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">
            {statusLabel}
          </span>
        )}
      </div>

      {chartPoints.length > 0 ? (
        <div className="mt-6 overflow-x-auto">
          <svg
            className="block h-auto w-full min-w-[520px]"
            viewBox={`0 0 ${chartWidth} ${chartHeight + 14}`}
            role="img"
            aria-labelledby="spending-chart-title spending-chart-description"
            preserveAspectRatio="xMidYMid meet"
          >
            <title id="spending-chart-title">
              Monthly spending ending {lastPoint?.label}
            </title>
            <desc id="spending-chart-description">
              {chartPoints.length} service-provided monthly spending values.
              Latest spending is {formatMoney(currentAmount, currency)}.
            </desc>
            <defs>
              <linearGradient id="spending-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2c9b67" stopOpacity="0.2" />
                <stop offset="100%" stopColor="#2c9b67" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[35, 75, 115].map((y) => (
              <line
                key={y}
                x1="0"
                x2={chartWidth}
                y1={y}
                y2={y}
                stroke="#e8edeb"
                strokeWidth="1"
                strokeDasharray="4 5"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <path d={areaPath} fill="url(#spending-area)" />
            <path
              d={linePath}
              fill="none"
              stroke="#2c9b67"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
            {chartPoints.map((point, index) => (
              <g key={point.monthStart}>
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={index === chartPoints.length - 1 ? 5 : 3}
                  fill="white"
                  stroke="#2c9b67"
                  strokeWidth={index === chartPoints.length - 1 ? 3 : 2}
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  x={point.x}
                  y={chartHeight + 13}
                  textAnchor="middle"
                  className="fill-slate-600 text-[10px] font-medium"
                >
                  {point.label}
                </text>
              </g>
            ))}
          </svg>
        </div>
      ) : (
        <p className="mt-6 rounded-xl bg-mist-50 px-4 py-5 text-center text-xs text-slate-600">
          No monthly spending is available yet.
        </p>
      )}
    </Card>
  );
}
