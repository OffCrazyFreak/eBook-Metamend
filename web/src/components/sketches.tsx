// Pencil sketches on the sheet: a few white shapes that draw themselves in,
// hold, and rub out again. Kept faint, doubled and roughened so they read as
// hand-drawn, and placed at the margins so the text column never has one
// behind it. Every sketch shares one 54 s cycle and lives for a third of it,
// so with six shapes staggered 9 s apart about two are on the sheet at once.

interface Sketch {
  d: string
  duration: number
  delay: number
}

const SKETCHES: Sketch[] = [
  // circle, top left, drawn twice slightly off
  { d: 'M 150 190 a 62 62 0 1 1 -1 -6', duration: 54, delay: 0 },
  { d: 'M 154 186 a 60 64 0 1 0 2 -4', duration: 54, delay: 0.6 },
  // square, bottom right
  { d: 'M 1180 640 h 130 v 128 h -132 z', duration: 54, delay: 9 },
  { d: 'M 1184 644 h 124 v 122 h -126 z', duration: 54, delay: 9.6 },
  // cube, right edge
  {
    d: 'M 1290 250 l 60 -32 l 60 32 v 68 l -60 32 l -60 -32 z M 1290 250 l 60 32 l 60 -32 M 1350 282 v 68',
    duration: 54,
    delay: 18,
  },
  // long arc across the bottom
  { d: 'M 60 820 Q 720 700 1400 830', duration: 54, delay: 27 },
  // dimension line with end ticks, top right
  { d: 'M 980 120 h 280 M 980 110 v 20 M 1260 110 v 20', duration: 54, delay: 36 },
  // small crosshair, left middle
  {
    d: 'M 90 520 h 70 M 125 485 v 70 M 125 520 m -22 0 a 22 22 0 1 0 44 0 a 22 22 0 1 0 -44 0',
    duration: 54,
    delay: 45,
  },
]

export function Sketches() {
  return (
    <svg
      className="bp-sketches"
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <filter id="pencil" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves="2"
            seed="7"
            result="noise"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="noise"
            scale="2.2"
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </defs>
      <g filter="url(#pencil)">
        {SKETCHES.map((s, i) => (
          <g
            key={i}
            style={{ animationDuration: `${s.duration}s`, animationDelay: `-${s.delay}s` }}
          >
            <path d={s.d} pathLength={1} />
            {/* the second pass of the pencil, a little off and lighter */}
            <path
              d={s.d}
              pathLength={1}
              transform="translate(1.5 1)"
              className="bp-sketch-second"
            />
          </g>
        ))}
      </g>
    </svg>
  )
}
