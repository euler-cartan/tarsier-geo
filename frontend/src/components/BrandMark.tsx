/**
 * The Tarsier mark (tarsier-logo-v2): a tarsier face with round ears and two ringed eyes.
 * The colours are the logo's own, fixed in every theme, as in the source SVG.
 */
function BrandMark({ size = 46 }: { size?: number }) {
  const plate = "#101014";
  const white = "#fafafa";
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden="true" focusable="false" fill="none" style={{ flexShrink: 0 }}>
      <g stroke={white} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="22" cy="36" r="11" fill={plate} />
        <circle cx="98" cy="36" r="11" fill={plate} />
        <rect x="14" y="30" width="92" height="68" rx="32" ry="32" fill={plate} />
        <circle cx="42" cy="64" r="17" fill={plate} />
        <circle cx="42" cy="64" r="10.54" fill={white} stroke="none" />
        <circle cx="44.72" cy="61.28" r="4.25" fill={plate} stroke="none" />
        <circle cx="78" cy="64" r="17" fill={plate} />
        <circle cx="78" cy="64" r="10.54" fill={white} stroke="none" />
        <circle cx="80.72" cy="61.28" r="4.25" fill={plate} stroke="none" />
      </g>
    </svg>
  );
}

export default BrandMark;
