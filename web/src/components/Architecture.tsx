"use client";

/** Isometric courtyard community, shared by the landing hero and the exploring screen. */
export default function Architecture() {
  return (
    <svg
      className="architecture"
      viewBox="0 0 600 480"
      fill="none"
      role="img"
      aria-label="Isometric courtyard and homes, conceptual illustration"
    >
      <defs>
        <linearGradient
          id="ground"
          x1="100"
          y1="120"
          x2="500"
          y2="440"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#efedf6" />
          <stop offset="1" stopColor="#faf9f6" />
        </linearGradient>
        <linearGradient id="roof" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#fff" />
          <stop offset="1" stopColor="#e9e6f0" />
        </linearGradient>
      </defs>
      <g className="architecture-float">
        <path
          d="m55 279 250-145 244 140-250 145Z"
          fill="url(#ground)"
          stroke="#d9d6df"
        />
        <path
          d="m55 279 244 140v12L55 291Zm244 140 250-145v12L299 431Z"
          fill="#e6e3eb"
          stroke="#d9d6df"
        />
        <g stroke="#dcd9e3" strokeWidth=".7">
          {[0, 1, 2, 3, 4, 5].map((n) => (
            <path
              key={n}
              d={`M${85 + n * 38} ${296 + n * 22} l250-145 M${95 + n * 40} ${256 - n * 23} l244 140`}
            />
          ))}
        </g>
        <path
          d="m166 285 136-79 139 80-140 82Z"
          fill="#e3e8e1"
          stroke="#cdd5cb"
        />
        <path
          d="m204 286 98-56 99 56-100 59Z"
          fill="#f8f7f3"
          stroke="#d5d3d8"
        />
        <path d="m231 288 71-41 68 40-69 40Z" fill="#e0e5dd" />
        {[
          [126, 250],
          [208, 201],
          [363, 246],
          [281, 294],
        ].map(([x, y], i) => (
          <g
            key={i}
            className="building"
            style={{ animationDelay: `${i * 130}ms` }}
          >
            <path
              d={`m${x} ${y} 55 32 52-30-55-32Z`}
              fill="#f2f0f6"
              stroke="#b9b4c4"
            />
            <path
              d={`m${x} ${y} v-59l55 32v59Z`}
              fill="#e5e1ed"
              stroke="#b9b4c4"
            />
            <path
              d={`m${x + 55} ${y + 32} v-59l52-30v59Z`}
              fill="#faf9fc"
              stroke="#b9b4c4"
            />
            <path
              d={`m${x} ${y - 59} 52-30 55 32-52 30Z`}
              fill="url(#roof)"
              stroke="#b9b4c4"
            />
            <path
              d={`m${x + 12} ${y - 26} 29 17v12l-29-17Zm52 20 29-17v12l-29 17Z`}
              fill="#b4b0c3"
            />
            <path d={`m${x + 64} ${y + 19} v-14l12-7v14`} stroke="#9a93ad" />
          </g>
        ))}
        {[
          [108, 289],
          [458, 277],
          [297, 366],
          [304, 211],
          [219, 317],
          [386, 324],
        ].map(([x, y], i) => (
          <g key={i}>
            <path d={`M${x} ${y}v-28`} stroke="#a5b09f" strokeWidth="2" />
            <ellipse
              cx={x}
              cy={y - 30}
              rx="13"
              ry="20"
              fill="#d2dbcd"
              stroke="#bfcbb9"
            />
            <path d={`M${x} ${y - 11}v-25`} stroke="#b0bea9" />
          </g>
        ))}
      </g>
      <path d="M56 370v34h35M515 149v-34h-35" stroke="#aaa3b7" />
      <text x="52" y="432" fill="#9c95a7" fontSize="9" letterSpacing="2">
        FORM · SPACE · POSSIBILITY
      </text>
    </svg>
  );
}
