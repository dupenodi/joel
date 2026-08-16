const reduceMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

function hasGsap() {
  return typeof window.gsap !== "undefined";
}

function setupHeroOrbitDots() {
  const orbit = document.querySelector(".hero-orbit");
  const dots = gsap.utils.toArray(".hero-orbit-dot", orbit);
  if (!orbit || !dots.length) return;

  const layout = () => {
    const radius = orbit.getBoundingClientRect().width / 2;
    dots.forEach((dot) => dot.style.setProperty("--orbit-radius", `${radius}px`));
  };

  layout();

  let frame = 0;
  window.addEventListener("resize", () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      layout();
      frame = 0;
    });
  });
}

function setupHero() {
  const items = gsap.utils.toArray(".js-hero");
  const orbit = document.querySelector(".hero-orbit");
  const joel = document.querySelector("#hero-joel");
  const stage = document.querySelector("#hero-logo-stage");
  const logo = document.querySelector("#hero-logo");
  const visual = document.querySelector(".hero-visual");
  const ask = document.querySelector("#hero-ask");
  const askLine = document.querySelector("#hero-ask-line");
  const speech = document.querySelector("#hero-speech");
  const lineEl = document.querySelector("#hero-speech-line");
  const statusEl = document.querySelector("#hero-speech-status");
  const citesEl = document.querySelector("#hero-speech-cites");

  if (
    !items.length ||
    !joel ||
    !stage ||
    !logo ||
    !visual ||
    !ask ||
    !askLine ||
    !speech ||
    !lineEl ||
    !statusEl ||
    !citesEl
  ) {
    return;
  }

  const iconFor = (tool) => {
    const files = {
      Slack: "slack.svg",
      HubSpot: "hubspot.svg",
      Jira: "jira.svg",
      Linear: "linear.svg",
      Notion: "notion.svg",
      Gmail: "gmail.svg",
      Drive: "googledrive.svg",
      GitHub: "github.svg",
      Confluence: "confluence.svg",
      Fireflies: "fireflies.svg",
    };
    const file = files[tool];
    if (!file) return "";
    return `<img class="hero-tool-icon" src="./icons/${file}" alt="" width="14" height="14" />`;
  };

  const renderStatus = (step) => {
    const tools = step.tools || (step.tool ? [step.tool] : []);
    const icons = tools.map(iconFor).join("");
    statusEl.innerHTML = `
      <span class="hero-speech-status-icons">${icons}</span>
      <span class="hero-speech-status-label">${step.status}</span>
    `;
  };

  const renderCites = (cites) => {
    citesEl.innerHTML = cites
      .map(
        (cite) =>
          `<span class="hero-cite">${iconFor(cite)}<span>${cite}</span></span>`
      )
      .join("");
    citesEl.hidden = false;
  };

  const demos = [
    {
      ask: "What did we promise Acme on SSO, and has eng actually started?",
      steps: [
        { status: "Reading Gmail…", tool: "Gmail", ms: 850 },
        { status: "Checking Notion…", tool: "Notion", ms: 800 },
        { status: "Scanning Jira…", tool: "Jira", ms: 750 },
        {
          status: "Linking sources…",
          tools: ["Gmail", "Notion", "Jira", "Slack"],
          ms: 800,
        },
      ],
      answer: "MSA says SSO by Sept 30. ENG-4412 In Progress — Alex, unblocked Monday.",
      cites: ["Gmail", "Notion", "Jira", "Slack"],
    },
    {
      ask: "Can we give Northwind 20% off without breaking gross margin?",
      steps: [
        { status: "Reading HubSpot…", tool: "HubSpot", ms: 800 },
        { status: "Checking Drive…", tool: "Drive", ms: 850 },
        { status: "Scanning Slack…", tool: "Slack", ms: 750 },
        {
          status: "Linking sources…",
          tools: ["HubSpot", "Drive", "Slack", "Notion"],
          ms: 800,
        },
      ],
      answer: "No — 20% drops them to 41% GM. CFO capped discretionary at 12% in #finance.",
      cites: ["HubSpot", "Drive", "Slack", "Notion"],
    },
    {
      ask: "What are the open risks on the mobile rewrite before Friday's board?",
      steps: [
        { status: "Reading Linear…", tool: "Linear", ms: 800 },
        { status: "Checking Confluence…", tool: "Confluence", ms: 800 },
        { status: "Scanning Slack…", tool: "Slack", ms: 750 },
        {
          status: "Linking sources…",
          tools: ["Linear", "Confluence", "Slack", "GitHub"],
          ms: 850,
        },
      ],
      answer: "Three: Auth rewrite slip, TestFlight crash rate, and no owner on offline sync.",
      cites: ["Linear", "Confluence", "Slack", "GitHub"],
    },
    {
      ask: "Who last changed the pricing page, and did legal sign off?",
      steps: [
        { status: "Reading GitHub…", tool: "GitHub", ms: 800 },
        { status: "Checking Gmail…", tool: "Gmail", ms: 800 },
        { status: "Scanning Notion…", tool: "Notion", ms: 750 },
        {
          status: "Linking sources…",
          tools: ["GitHub", "Gmail", "Notion", "Slack"],
          ms: 800,
        },
      ],
      answer: "Sam merged #884 Tue. Legal approved in thread — Maya, with one caveat on EU copy.",
      cites: ["GitHub", "Gmail", "Notion", "Slack"],
    },
  ];

  if (reduceMotionQuery.matches) {
    const demo = demos[0];
    gsap.set(items, { opacity: 1, y: 0 });
    gsap.set([joel, orbit], { opacity: 1, scale: 1 });
    askLine.textContent = demo.ask;
    lineEl.textContent = demo.answer;
    renderCites(demo.cites);
    ask.classList.add("is-open");
    speech.classList.add("is-open");
    gsap.set([ask, speech], { opacity: 1, scale: 1 });
    ask.setAttribute("aria-hidden", "false");
    speech.setAttribute("aria-hidden", "false");
    return;
  }

  /*
    Hero flow
    ---------
    1. Orbit in → Joel lands → copy arrives
    2. Idle (float, breathe, rare glances)
    3. Quiet beat
    4. Demo loop (occasional):
       ask → retrieve steps → answer + cites → hold → clear
    5. Long quiet, then next demo
  */

  gsap.set(items, { opacity: 0, y: 22 });
  gsap.set(joel, { opacity: 0, scale: 0.78, rotateY: -22, rotateX: 4 });
  gsap.set(orbit, { opacity: 0, scale: 0.9 });
  gsap.set(ask, { opacity: 0, scale: 0.88, rotate: -4, y: 8 });
  gsap.set(speech, { opacity: 0, scale: 0.84, rotate: 4, y: 10 });
  askLine.textContent = "";
  lineEl.textContent = "";
  statusEl.innerHTML = "";
  citesEl.innerHTML = "";
  citesEl.hidden = true;

  let idleFloat;
  let idleBreathe;
  let tracking = false;
  let speaking = false;
  let lookTimer = 0;
  let lookTween;
  let speechTimer = 0;
  let demoIndex = 0;
  let frame = 0;
  let rotX = 0;
  let rotY = 0;
  let idleReady = false;

  const pupil = { x: 0, y: 0 };
  const syncPupils = () => {
    logo.style.setProperty("--joel-pupil-x", `${pupil.x.toFixed(2)}px`);
    logo.style.setProperty("--joel-pupil-y", `${pupil.y.toFixed(2)}px`);
  };
  const pupilXTo = gsap.quickTo(pupil, "x", {
    duration: 0.35,
    ease: "power2.out",
    onUpdate: syncPupils,
  });
  const pupilYTo = gsap.quickTo(pupil, "y", {
    duration: 0.35,
    ease: "power2.out",
    onUpdate: syncPupils,
  });
  const rotateXTo = gsap.quickTo(joel, "rotateX", { duration: 0.45, ease: "power2.out" });
  const rotateYTo = gsap.quickTo(joel, "rotateY", { duration: 0.45, ease: "power2.out" });

  const setPupils = (x, y) => {
    pupilXTo(x);
    pupilYTo(y);
  };

  const wait = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  const pauseIdle = () => {
    idleFloat?.pause();
    idleBreathe?.pause();
  };

  const resumeIdle = () => {
    if (!idleReady || speaking) return;
    idleFloat?.play();
    if (idleBreathe) {
      idleBreathe.kill();
      idleBreathe = gsap.fromTo(
        joel,
        { scale: 1 },
        {
          scale: 1.03,
          duration: 3.2,
          ease: "sine.inOut",
          repeat: -1,
          yoyo: true,
        }
      );
    }
  };

  const startIdle = () => {
    idleFloat = gsap.to(joel, {
      keyframes: [
        { y: -16, duration: 2.2 },
        { y: -4, duration: 2.1 },
        { y: -14, duration: 2.3 },
        { y: 0, duration: 2.1 },
      ],
      ease: "sine.inOut",
      repeat: -1,
    });

    idleBreathe = gsap.to(joel, {
      scale: 1.03,
      duration: 3.2,
      ease: "sine.inOut",
      repeat: -1,
      yoyo: true,
    });

    idleReady = true;
  };

  const scheduleCuriousLook = () => {
    window.clearTimeout(lookTimer);
    lookTween?.kill();

    lookTimer = window.setTimeout(() => {
      if (tracking || speaking) {
        scheduleCuriousLook();
        return;
      }

      const glances = [
        { x: 7, y: -3 },
        { x: -8, y: 2 },
        { x: 0, y: 0 },
      ];

      lookTween = gsap.timeline({ onComplete: scheduleCuriousLook });
      glances.forEach((glance, index) => {
        lookTween.to(
          pupil,
          {
            x: glance.x,
            y: glance.y,
            duration: 0.5,
            ease: "power2.inOut",
            onUpdate: syncPupils,
          },
          index === 0 ? 0 : "+=0.7"
        );
      });
    }, 3200 + Math.random() * 3600);
  };

  const showBubble = (el, vars) =>
    new Promise((resolve) => {
      el.classList.add("is-open");
      el.setAttribute("aria-hidden", "false");
      gsap.to(el, {
        ...vars,
        duration: 0.42,
        ease: "back.out(1.5)",
        onComplete: resolve,
      });
    });

  const hideBubble = (el, vars) =>
    new Promise((resolve) => {
      gsap.to(el, {
        ...vars,
        duration: 0.3,
        ease: "power2.in",
        onComplete: () => {
          el.classList.remove("is-open");
          el.setAttribute("aria-hidden", "true");
          resolve();
        },
      });
    });

  const typeLine = (text) =>
    new Promise((resolve) => {
      let char = 0;
      speech.classList.add("is-typing");
      lineEl.textContent = "";

      const step = () => {
        char += 1;
        lineEl.textContent = text.slice(0, char);
        if (char >= text.length) {
          speech.classList.remove("is-typing");
          resolve();
          return;
        }
        window.setTimeout(step, text[char - 1] === " " ? 34 : 26);
      };

      step();
    });

  const runDemo = async (demo) => {
    speaking = true;
    lookTween?.kill();
    window.clearTimeout(lookTimer);
    pauseIdle();

    askLine.textContent = demo.ask;
    lineEl.textContent = "";
    statusEl.innerHTML = "";
    citesEl.innerHTML = "";
    citesEl.hidden = true;
    speech.classList.remove("is-working", "is-typing");

    // 1) question arrives
    await gsap.to(pupil, {
      x: -8,
      y: -3,
      duration: 0.3,
      ease: "power2.out",
      onUpdate: syncPupils,
    });
    await showBubble(ask, { opacity: 1, scale: 1, y: 0, rotate: -1.5 });
    await wait(900);

    // 2) joel turns to work
    await gsap.to(pupil, {
      x: 9,
      y: -4,
      duration: 0.35,
      ease: "power2.out",
      onUpdate: syncPupils,
    });

    speech.classList.add("is-working");
    renderStatus(demo.steps[0]);
    await showBubble(speech, { opacity: 1, scale: 1, y: 0, rotate: 1.5 });

    // 3) retrieve / process steps
    for (const step of demo.steps) {
      renderStatus(step);
      const icons = statusEl.querySelector(".hero-speech-status-icons");
      if (icons) {
        gsap.fromTo(
          icons.children,
          { opacity: 0, scale: 0.7 },
          { opacity: 1, scale: 1, duration: 0.28, stagger: 0.05, ease: "back.out(1.6)" }
        );
      }
      await wait(step.ms);
    }

    // 4) answer
    speech.classList.remove("is-working");
    statusEl.innerHTML = "";
    await typeLine(demo.answer);

    renderCites(demo.cites);
    gsap.fromTo(
      citesEl.children,
      { opacity: 0, y: 4 },
      { opacity: 1, y: 0, duration: 0.35, stagger: 0.06, ease: "power2.out" }
    );

    await wait(3200);

    // 5) clear both
    await Promise.all([
      hideBubble(ask, { opacity: 0, scale: 0.9, y: 6, rotate: -4 }),
      hideBubble(speech, { opacity: 0, scale: 0.9, y: 8, rotate: 4 }),
    ]);

    askLine.textContent = "";
    lineEl.textContent = "";
    statusEl.innerHTML = "";
    citesEl.innerHTML = "";
    citesEl.hidden = true;
    speech.classList.remove("is-working", "is-typing");

    await gsap.to(pupil, {
      x: 0,
      y: 0,
      duration: 0.35,
      ease: "power2.out",
      onUpdate: syncPupils,
    });

    speaking = false;
    if (!tracking) {
      resumeIdle();
      scheduleCuriousLook();
    }
  };

  const scheduleDemo = (delayMs) => {
    window.clearTimeout(speechTimer);
    speechTimer = window.setTimeout(async () => {
      if (tracking) {
        scheduleDemo(1600);
        return;
      }

      const demo = demos[demoIndex % demos.length];
      demoIndex += 1;
      await runDemo(demo);
      scheduleDemo(900 + Math.random() * 700);
    }, delayMs);
  };

  const track = (event) => {
    tracking = true;
    window.clearTimeout(lookTimer);
    lookTween?.kill();

    const bounds = visual.getBoundingClientRect();
    const cx = bounds.left + bounds.width / 2;
    const cy = bounds.top + bounds.height / 2;
    const nx = Math.max(-1, Math.min(1, (event.clientX - cx) / (bounds.width / 2)));
    const ny = Math.max(-1, Math.min(1, (event.clientY - cy) / (bounds.height / 2)));

    rotY = nx * 14;
    rotX = -ny * 10;

    if (!frame) {
      frame = requestAnimationFrame(() => {
        rotateXTo(rotX);
        rotateYTo(rotY);
        if (!speaking) setPupils(nx * 8, ny * 5);
        frame = 0;
      });
    }
  };

  const reset = () => {
    tracking = false;
    rotX = 0;
    rotY = 0;
    rotateXTo(0);
    rotateYTo(0);
    if (!speaking) setPupils(0, 0);
    gsap.to(joel, {
      scale: 1,
      duration: 0.5,
      ease: "power2.out",
      overwrite: "auto",
      onComplete: resumeIdle,
    });
    if (!speaking) scheduleCuriousLook();
  };

  const greet = () => {
    tracking = true;
    window.clearTimeout(lookTimer);
    lookTween?.kill();
    if (!speaking) pauseIdle();
    gsap.to(joel, {
      scale: 1.05,
      duration: 0.26,
      ease: "power2.out",
      overwrite: "auto",
      yoyo: true,
      repeat: 1,
    });
  };

  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
  if (finePointer.matches) {
    visual.addEventListener("pointerenter", greet);
    visual.addEventListener("pointermove", track, { passive: true });
    visual.addEventListener("pointerleave", reset);
  }

  const entrance = gsap.timeline({
    defaults: { ease: "power3.out" },
    onComplete: () => {
      startIdle();
      scheduleCuriousLook();
      scheduleDemo(1400);
    },
  });

  entrance
    .to(orbit, { opacity: 1, scale: 1, duration: 0.95 }, 0)
    .to(
      joel,
      { opacity: 1, scale: 1, rotateY: 0, rotateX: 0, duration: 1.1, ease: "power3.out" },
      0.12
    )
    .to(items, { opacity: 1, y: 0, duration: 0.7, stagger: 0.08 }, 0.28);
}

function layoutOrbit(positions) {
  const stage = document.querySelector("#orbit-stage");
  if (!stage) return { radius: 0, size: 0 };

  const size = stage.getBoundingClientRect().width;
  const chip = positions[0]?.querySelector(".chip");
  const chipSize = Math.max(chip?.offsetWidth || 108, chip?.offsetHeight || 106);
  const radius = Math.max(0, size / 2 - chipSize / 2 - 12);

  positions.forEach((el, i) => {
    const angle = (i / positions.length) * Math.PI * 2 - Math.PI / 2;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    el.style.setProperty("--x", `${x}px`);
    el.style.setProperty("--y", `${y}px`);
    el.dataset.angle = String(angle);
    el.dataset.x = String(x);
    el.dataset.y = String(y);
  });

  return { radius, size };
}

function buildOrbitLines(positions, size) {
  const svg = document.querySelector("#orbit-lines");
  if (!svg) return [];

  svg.setAttribute("viewBox", `${-size / 2} ${-size / 2} ${size} ${size}`);
  svg.innerHTML = "";

  return positions.map((pos) => {
    const angle = parseFloat(pos.dataset.angle || "0");
    const x = parseFloat(pos.dataset.x || "0");
    const y = parseFloat(pos.dataset.y || "0");
    const perpX = -Math.sin(angle);
    const perpY = Math.cos(angle);
    const bow = Math.hypot(x, y) * 0.16;
    const cx = x / 2 + perpX * bow;
    const cy = y / 2 + perpY * bow;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("class", "orbit-line");
    path.setAttribute("d", `M 0 0 Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}`);
    svg.appendChild(path);

    const pulse = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    pulse.setAttribute("class", "orbit-pulse");
    pulse.setAttribute("r", "3.5");
    svg.appendChild(pulse);

    return { path, pulse };
  });
}

function setupOrbit() {
  const stage = document.querySelector("#orbit-stage");
  const ring = document.querySelector("#orbit-ring");
  const positions = gsap.utils.toArray(".chip-position", ring);
  const chips = gsap.utils.toArray(".chip", ring);

  if (!stage || !ring || !positions.length) return;

  let layout = layoutOrbit(positions);
  let links = buildOrbitLines(positions, layout.size);

  let resizeFrame = 0;
  window.addEventListener("resize", () => {
    if (resizeFrame) return;
    resizeFrame = requestAnimationFrame(() => {
      layout = layoutOrbit(positions);
      links = buildOrbitLines(positions, layout.size);
      gsap.set(
        links.map((l) => l.path),
        { drawSVG: "100%" }
      );
      resizeFrame = 0;
    });
  });

  if (reduceMotionQuery.matches) {
    gsap.set(chips, { opacity: 1, scale: 1, x: 0, y: 0 });
    gsap.set(
      links.map((l) => l.path),
      { drawSVG: "100%" }
    );
    return;
  }

  const flyDistance = Math.min(90, Math.max(20, layout.radius * 0.24));
  chips.forEach((chip, i) => {
    const angle = parseFloat(positions[i].dataset.angle || "0");
    gsap.set(chip, {
      opacity: 0,
      scale: 0.4,
      x: Math.cos(angle) * flyDistance,
      y: Math.sin(angle) * flyDistance,
    });
  });

  gsap.set(
    links.map((l) => l.path),
    { drawSVG: "0%" }
  );
  gsap.set(
    links.map((l) => l.pulse),
    { opacity: 0 }
  );

  const startPulseLoop = () => {
    if (!links.length) return;

    links.forEach((link, i) => {
      const pulseTl = gsap.timeline({
        repeat: -1,
        repeatDelay: 2.8,
        delay: i * 0.45,
      });

      pulseTl
        .set(link.pulse, { opacity: 0 })
        .to(link.pulse, { opacity: 1, duration: 0.2 }, 0)
        .to(
          link.pulse,
          {
            motionPath: {
              path: link.path,
              align: link.path,
              alignOrigin: [0.5, 0.5],
              start: 1,
              end: 0,
            },
            duration: 1.35,
            ease: "power1.inOut",
          },
          0
        )
        .to(link.pulse, { opacity: 0, duration: 0.2 }, "-=0.2");
    });
  };

  const startIdleOrbit = () => {
    gsap.to(ring, {
      rotation: "+=360",
      duration: 90,
      ease: "none",
      repeat: -1,
    });
    gsap.to(chips, {
      rotation: "-=360",
      duration: 90,
      ease: "none",
      repeat: -1,
    });

    startPulseLoop();
  };

  ScrollTrigger.create({
    trigger: stage,
    start: "top 78%",
    once: true,
    onEnter: () => {
      const tl = gsap.timeline({ onComplete: startIdleOrbit });

      tl.to(
        links.map((l) => l.path),
        {
          drawSVG: "100%",
          duration: 0.9,
          ease: "power2.out",
          stagger: { each: 0.07, from: "random" },
        },
        0
      ).to(
        chips,
        {
          opacity: 1,
          scale: 1,
          x: 0,
          y: 0,
          duration: 1.1,
          ease: "power3.out",
          stagger: { each: 0.07, from: "random" },
        },
        0
      );
    },
  });
}

function setupMobileNav() {
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector("#site-nav");
  const header = document.querySelector(".site-header");
  if (!toggle || !nav || !header) return;

  const setOpen = (open) => {
    header.classList.toggle("is-nav-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  };

  toggle.addEventListener("click", () => {
    setOpen(!header.classList.contains("is-nav-open"));
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => setOpen(false));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });

  window.matchMedia("(min-width: 681px)").addEventListener("change", (event) => {
    if (event.matches) setOpen(false);
  });
}

function setupArch() {
  const diagram = document.querySelector("#arch-diagram");
  const svg = document.querySelector("#arch-wires");
  if (!diagram || !svg) return;

  const node = (name) => diagram.querySelector(`[data-node="${name}"]`);
  const nodes = {
    connectors: node("connectors"),
    normalize: node("normalize"),
    distill: node("distill"),
    sqlite: node("sqlite"),
    vectors: node("vectors"),
    hydradb: node("hydradb"),
    link: node("link"),
    question: node("question"),
    retrieve: node("retrieve"),
    answer: node("answer"),
  };

  if (Object.values(nodes).some((el) => !el)) return;

  const tools = gsap.utils.toArray(".arch-tool", nodes.connectors);
  const stages = [
    nodes.normalize,
    nodes.distill,
    nodes.sqlite,
    nodes.vectors,
    nodes.hydradb,
    nodes.link,
    nodes.question,
    nodes.retrieve,
    nodes.answer,
  ];
  const edges = gsap.utils.toArray(".arch-edges span", nodes.link);

  const centerOf = (el, rootRect) => {
    const rect = el.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2 - rootRect.left,
      y: rect.top + rect.height / 2 - rootRect.top,
      top: rect.top - rootRect.top,
      bottom: rect.bottom - rootRect.top,
      left: rect.left - rootRect.left,
      right: rect.right - rootRect.left,
    };
  };

  const makePath = (d) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("class", "arch-wire");
    path.setAttribute("d", d);
    svg.appendChild(path);

    const pulse = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    pulse.setAttribute("class", "arch-pulse");
    pulse.setAttribute("r", "3.5");
    svg.appendChild(pulse);

    return { path, pulse };
  };

  const buildWires = () => {
    const root = diagram.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${root.width} ${root.height}`);
    svg.innerHTML = "";

    const c = centerOf(nodes.connectors, root);
    const n = centerOf(nodes.normalize, root);
    const d = centerOf(nodes.distill, root);
    const s = centerOf(nodes.sqlite, root);
    const v = centerOf(nodes.vectors, root);
    const h = centerOf(nodes.hydradb, root);
    const l = centerOf(nodes.link, root);
    const q = centerOf(nodes.question, root);
    const r = centerOf(nodes.retrieve, root);
    const a = centerOf(nodes.answer, root);

    const vertical = (from, to) =>
      `M ${from.x.toFixed(1)} ${from.bottom.toFixed(1)} L ${to.x.toFixed(1)} ${to.top.toFixed(1)}`;

    const curve = (from, to) => {
      const midY = (from.bottom + to.top) / 2;
      return `M ${from.x.toFixed(1)} ${from.bottom.toFixed(1)} C ${from.x.toFixed(1)} ${midY.toFixed(1)} ${to.x.toFixed(1)} ${midY.toFixed(1)} ${to.x.toFixed(1)} ${to.top.toFixed(1)}`;
    };

    const horizontal = (from, to) =>
      `M ${from.right.toFixed(1)} ${from.y.toFixed(1)} L ${to.left.toFixed(1)} ${to.y.toFixed(1)}`;

    // Stages reflow between a row and a single column at different widths, so
    // each wire takes its shape from where the nodes actually landed. Stacked
    // stores chain into each other instead of fanning, which would mean
    // crossing a card to reach the one below it.
    const storesInRow = v.top < s.bottom;
    const askInRow = r.left >= q.right;

    return {
      toNormalize: [makePath(vertical(c, n))],
      toDistill: [makePath(vertical(n, d))],
      toStore: storesInRow
        ? [makePath(curve(d, s)), makePath(curve(d, v)), makePath(curve(d, h))]
        : [makePath(curve(d, s)), makePath(curve(s, v)), makePath(curve(v, h))],
      toLink: storesInRow
        ? [makePath(curve(s, l)), makePath(curve(v, l)), makePath(curve(h, l))]
        : [makePath(curve(h, l))],
      toQuestion: [makePath(vertical(l, q))],
      toRetrieve: [askInRow ? makePath(horizontal(q, r)) : makePath(curve(q, r))],
      toAnswer: [askInRow ? makePath(horizontal(r, a)) : makePath(curve(r, a))],
    };
  };

  const flatten = (groups) => Object.values(groups).flat();
  const pathsOf = (group) => group.map((wire) => wire.path);

  let wires = buildWires();
  let allWires = flatten(wires);
  let pulseTweens = [];

  const startPulseLoop = () => {
    pulseTweens.forEach((t) => t.kill());
    pulseTweens = [];

    allWires.forEach((wire, i) => {
      const tl = gsap.timeline({
        repeat: -1,
        repeatDelay: 2.8,
        delay: i * 0.18,
      });

      tl.set(wire.pulse, { opacity: 0 })
        .to(wire.pulse, { opacity: 1, duration: 0.15 }, 0)
        .to(
          wire.pulse,
          {
            motionPath: {
              path: wire.path,
              align: wire.path,
              alignOrigin: [0.5, 0.5],
            },
            duration: 1.05,
            ease: "power1.inOut",
          },
          0
        )
        .to(wire.pulse, { opacity: 0, duration: 0.15 }, "-=0.15");

      pulseTweens.push(tl);
    });
  };

  let revealed = reduceMotionQuery.matches;

  let resizeFrame = 0;
  window.addEventListener("resize", () => {
    if (resizeFrame) return;
    resizeFrame = requestAnimationFrame(() => {
      pulseTweens.forEach((t) => t.kill());
      pulseTweens = [];
      wires = buildWires();
      allWires = flatten(wires);
      gsap.set(
        allWires.map((w) => w.path),
        { drawSVG: revealed ? "100%" : "0%" }
      );
      gsap.set(
        allWires.map((w) => w.pulse),
        { opacity: 0 }
      );
      if (revealed && !reduceMotionQuery.matches) startPulseLoop();
      resizeFrame = 0;
    });
  });

  if (reduceMotionQuery.matches) {
    gsap.set([...tools, ...stages, ...edges], { opacity: 1, y: 0, scale: 1 });
    gsap.set(
      allWires.map((w) => w.path),
      { drawSVG: "100%" }
    );
    return;
  }

  gsap.set(tools, { opacity: 0, y: -12, scale: 0.85 });
  gsap.set(stages, { opacity: 0, y: 22 });
  gsap.set(edges, { opacity: 0, scale: 0.85 });
  gsap.set(
    allWires.map((w) => w.path),
    { drawSVG: "0%" }
  );
  gsap.set(
    allWires.map((w) => w.pulse),
    { opacity: 0 }
  );

  ScrollTrigger.create({
    trigger: diagram,
    start: "top 70%",
    once: true,
    onEnter: () => {
      revealed = true;

      const tl = gsap.timeline({
        defaults: { ease: "power3.out" },
        onComplete: startPulseLoop,
      });

      tl.to(tools, { opacity: 1, y: 0, scale: 1, duration: 0.55, stagger: 0.04 }, 0)
        .to(nodes.normalize, { opacity: 1, y: 0, duration: 0.55 }, 0.25)
        .to(pathsOf(wires.toNormalize), { drawSVG: "100%", duration: 0.45 }, 0.3)
        .to(nodes.distill, { opacity: 1, y: 0, duration: 0.55 }, 0.5)
        .to(pathsOf(wires.toDistill), { drawSVG: "100%", duration: 0.45 }, 0.55)
        .to(
          [nodes.sqlite, nodes.vectors, nodes.hydradb],
          { opacity: 1, y: 0, duration: 0.55, stagger: 0.08 },
          0.75
        )
        .to(
          pathsOf(wires.toStore),
          { drawSVG: "100%", duration: 0.55, stagger: 0.06 },
          0.8
        )
        .to(nodes.link, { opacity: 1, y: 0, duration: 0.55 }, 1.15)
        .to(
          pathsOf(wires.toLink),
          { drawSVG: "100%", duration: 0.5, stagger: 0.05 },
          1.2
        )
        .to(edges, { opacity: 1, scale: 1, duration: 0.4, stagger: 0.05 }, 1.4)
        .to(nodes.question, { opacity: 1, y: 0, duration: 0.5 }, 1.55)
        .to(pathsOf(wires.toQuestion), { drawSVG: "100%", duration: 0.4 }, 1.6)
        .to(nodes.retrieve, { opacity: 1, y: 0, duration: 0.45 }, 1.75)
        .to(pathsOf(wires.toRetrieve), { drawSVG: "100%", duration: 0.35 }, 1.8)
        .to(nodes.answer, { opacity: 1, y: 0, duration: 0.55, ease: "back.out(1.2)" }, 1.95)
        .to(pathsOf(wires.toAnswer), { drawSVG: "100%", duration: 0.35 }, 2.0);
    },
  });
}

function init() {
  setupMobileNav();

  if (!hasGsap()) return;

  gsap.registerPlugin(ScrollTrigger, MotionPathPlugin, DrawSVGPlugin);

  setupHero();
  setupHeroOrbitDots();
  setupOrbit();
  setupArch();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
