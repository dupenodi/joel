const template = document.createElement("template");

template.innerHTML = `
  <style>
    :host {
      --joel-logo-size: 16rem;
      --joel-spin-2d-duration: 8s;
      --joel-spin-3d-duration: 6s;
      --joel-blink-duration: 5s;
      --joel-perspective: 900px;
      display: inline-block;
      width: var(--joel-logo-size);
      height: var(--joel-logo-size);
      contain: layout style;
    }

    .scene,
    .background-layer,
    .mark-layer,
    .spin-3d,
    .spin-2d,
    svg {
      display: block;
      width: 100%;
      height: 100%;
    }

    .scene {
      position: relative;
      perspective: var(--joel-perspective);
    }

    .background-layer,
    .mark-layer {
      position: absolute;
      inset: 0;
    }

    .spin-3d,
    .spin-2d {
      transform-origin: 50% 50%;
      transform-style: preserve-3d;
      will-change: transform;
    }

    :host([effects~="spin-2d"]) .spin-2d {
      animation: joel-spin-2d var(--joel-spin-2d-duration) linear infinite;
    }

    :host([effects~="spin-3d"]) .spin-3d {
      animation: joel-spin-3d var(--joel-spin-3d-duration) ease-in-out infinite;
    }

    .eye {
      transform-box: fill-box;
      transform-origin: center;
      will-change: transform;
    }

    :host([effects~="blink"]) .eye {
      animation: joel-blink var(--joel-blink-duration) ease-in-out infinite;
    }

    :host([paused]) *,
    :host(:hover[hover-pause]) * {
      animation-play-state: paused !important;
    }

    @keyframes joel-spin-2d {
      to { transform: rotate(1turn); }
    }

    @keyframes joel-spin-3d {
      0%, 100% { transform: rotateY(-24deg) rotateX(5deg); }
      50% { transform: rotateY(204deg) rotateX(-5deg); }
    }

    @keyframes joel-blink {
      0%, 46%, 50%, 100% { transform: scaleY(1); }
      48% { transform: scaleY(0.06); }
    }

    @media (prefers-reduced-motion: reduce) {
      :host(:not([force-motion])) * {
        animation: none !important;
      }
    }
  </style>

  <div class="scene" part="scene">
    <svg
      class="background-layer"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 512 512"
      role="img"
      aria-labelledby="title"
    >
      <title id="title">Joel logo</title>
      <rect class="background" width="512" height="512" rx="112"/>
    </svg>

    <div class="mark-layer">
      <div class="spin-3d" part="spin-3d">
        <div class="spin-2d" part="spin-2d">
          <svg
            part="mark"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 512 512"
            aria-hidden="true"
          >
            <g transform="translate(256 256) skewY(-10) translate(-256 -256)">
              <g class="shadow" transform="translate(268, 268)">
                <rect x="-34" y="-155" width="68" height="310" rx="26"/>
                <rect x="-34" y="-155" width="68" height="310" rx="26" transform="rotate(45)"/>
                <rect x="-34" y="-155" width="68" height="310" rx="26" transform="rotate(90)"/>
                <rect x="-34" y="-155" width="68" height="310" rx="26" transform="rotate(135)"/>
              </g>

              <g transform="translate(252, 252)">
                <g class="mark-outer">
                  <rect x="-34" y="-155" width="68" height="310" rx="26"/>
                  <rect x="-34" y="-155" width="68" height="310" rx="26" transform="rotate(45)"/>
                  <rect x="-34" y="-155" width="68" height="310" rx="26" transform="rotate(90)"/>
                  <rect x="-34" y="-155" width="68" height="310" rx="26" transform="rotate(135)"/>
                </g>

                <g class="mark-inner">
                  <rect x="-23" y="-145" width="46" height="290" rx="18"/>
                  <rect x="-23" y="-145" width="46" height="290" rx="18" transform="rotate(45)"/>
                  <rect x="-23" y="-145" width="46" height="290" rx="18" transform="rotate(90)"/>
                  <rect x="-23" y="-145" width="46" height="290" rx="18" transform="rotate(135)"/>
                </g>

                <g transform="scale(0.78)">
                  <g class="eye">
                    <path d="M -68,-8 C -46,-42 -20,-60 4,-60 C 30,-60 54,-40 68,-8 Q 74,0 68,8 C 48,40 24,60 -4,60 C -32,60 -56,40 -68,8 Q -74,0 -68,-8 Z"/>
                    <ellipse class="pupil" cx="0" cy="0" rx="22" ry="34"/>
                  </g>
                </g>
              </g>
            </g>
          </svg>
        </div>
      </div>
    </div>
  </div>
`;

const palettes = {
  red: {
    background: "#FF2D2D",
    shadow: "#000000",
    outer: "#000000",
    inner: "#FFFFFF",
    eye: "#000000",
    pupil: "#FFFFFF",
  },
  light: {
    background: "#F7F5F2",
    shadow: "#FF2D2D",
    outer: "#000000",
    inner: "#FFFFFF",
    eye: "#000000",
    pupil: "#FFFFFF",
  },
  dark: {
    background: "#111111",
    shadow: "#FF2D2D",
    outer: "#FFFFFF",
    inner: "#111111",
    eye: "#FFFFFF",
    pupil: "#111111",
  },
};

class JoelLogo extends HTMLElement {
  static observedAttributes = ["variant", "label"];

  constructor() {
    super();
    this.attachShadow({ mode: "open" }).append(template.content.cloneNode(true));
  }

  connectedCallback() {
    this.#render();
  }

  attributeChangedCallback() {
    this.#render();
  }

  #render() {
    if (!this.shadowRoot) return;

    const palette = palettes[this.getAttribute("variant")] ?? palettes.red;
    const label = this.getAttribute("label") || "Joel logo";

    this.shadowRoot.querySelector("title").textContent = label;
    this.shadowRoot.querySelector(".background").style.fill = palette.background;
    this.shadowRoot.querySelector(".shadow").style.fill = palette.shadow;
    this.shadowRoot.querySelector(".mark-outer").style.fill = palette.outer;
    this.shadowRoot.querySelector(".mark-inner").style.fill = palette.inner;
    this.shadowRoot.querySelector(".eye path").style.fill = palette.eye;
    this.shadowRoot.querySelector(".pupil").style.fill = palette.pupil;
  }
}

if (!customElements.get("joel-logo")) {
  customElements.define("joel-logo", JoelLogo);
}
