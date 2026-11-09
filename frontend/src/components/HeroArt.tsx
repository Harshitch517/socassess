// Decorative vector illustration: a shield watching over a small network of systems.
// Pure SVG (sharp at any resolution, follows the theme colours); hidden from screen readers.
export default function HeroArt({ className = "" }: { className?: string }) {
  const nodes = [
    [40, 150], [95, 205], [70, 60], [250, 45], [300, 130], [275, 215], [180, 235],
  ];
  return (
    <svg viewBox="0 0 340 260" className={className} aria-hidden focusable="false">
      <defs>
        <linearGradient id="hero-shield" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--accent)" />
          <stop offset="100%" stopColor="var(--series-7)" />
        </linearGradient>
        <radialGradient id="hero-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="170" cy="130" r="120" fill="url(#hero-glow)" />
      {/* network links */}
      {nodes.map(([x, y], i) => (
        <line key={`l${i}`} x1="170" y1="130" x2={x} y2={y} stroke="var(--accent)" strokeOpacity="0.35" strokeWidth="1.5" strokeDasharray="4 5" />
      ))}
      <polyline points={nodes.map((n) => n.join(",")).join(" ")} fill="none" stroke="var(--ink-2)" strokeOpacity="0.18" strokeWidth="1" />
      {/* systems */}
      {nodes.map(([x, y], i) => (
        <g key={`n${i}`}>
          {i % 3 === 0 && <circle className="pulse-ring" cx={x} cy={y} r="6" fill="none" stroke="var(--accent)" strokeWidth="1.5" />}
          <rect x={x - 11} y={y - 8} width="22" height="16" rx="3.5" fill="var(--surface-1)" stroke="var(--accent)" strokeWidth="1.6" />
          <line x1={x - 6} y1={y - 2} x2={x + 6} y2={y - 2} stroke="var(--accent)" strokeWidth="1.4" strokeLinecap="round" />
          <line x1={x - 6} y1={y + 3} x2={x + 2} y2={y + 3} stroke="var(--accent)" strokeOpacity="0.6" strokeWidth="1.4" strokeLinecap="round" />
        </g>
      ))}
      {/* shield */}
      <g className="float">
        <path d="M170 72 L214 88 V128 C214 158 195 178 170 190 C145 178 126 158 126 128 V88 Z"
          fill="url(#hero-shield)" stroke="var(--surface-1)" strokeWidth="3" />
        <path d="M152 131 L165 144 L189 117" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
