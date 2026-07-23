import { ArrowDownRight } from 'lucide-react';

import { spendingPoints } from '../../lib/demo-data';
import { Card } from './Card';

const chartWidth = 620;
const chartHeight = 150;
const maxAmount = 24_000;
const horizontalInset = 10;

const chartPoints = spendingPoints.map((point, index) => {
  const x =
    horizontalInset +
    (index * (chartWidth - horizontalInset * 2)) / (spendingPoints.length - 1);
  const y = chartHeight - (point.amount / maxAmount) * (chartHeight - 18);
  return { ...point, x, y };
});

const linePath = chartPoints
  .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
  .join(' ');

const areaPath = `${linePath} L ${chartPoints.at(-1)?.x ?? chartWidth} ${chartHeight} L ${chartPoints[0]?.x ?? 0} ${chartHeight} Z`;

export function SpendingTrend() {
  return (
    <Card className="min-w-0 p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">Spending trend</p>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <p className="text-2xl font-semibold tracking-[-0.035em] text-slate-900">
              ₹18,540
            </p>
            <span className="text-leaf-700 inline-flex items-center gap-1 text-xs font-semibold">
              <ArrowDownRight className="size-3.5" aria-hidden="true" />
              8.2%
            </span>
          </div>
          <p className="mt-1 text-[11px] font-medium text-slate-600">
            Compared with last month
          </p>
        </div>
        <span className="rounded-full bg-mist-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">
          Synthetic
        </span>
      </div>

      <div className="mt-6 overflow-x-auto">
        <svg
          className="block h-auto w-full min-w-[520px]"
          viewBox={`0 0 ${chartWidth} ${chartHeight + 14}`}
          role="img"
          aria-labelledby="spending-chart-title spending-chart-description"
          preserveAspectRatio="xMidYMid meet"
        >
          <title id="spending-chart-title">
            Monthly spending from February to July
          </title>
          <desc id="spending-chart-description">
            Synthetic preview values show spending rising from ₹14,200 in
            February to a high of ₹21,300 in May, then easing to ₹18,540 in
            July.
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
            <g key={point.label}>
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
    </Card>
  );
}
