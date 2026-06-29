(() => {
  const dashboard = document.querySelector("#dashboard");
  const jokerCard = document.querySelector("#joker-card");
  const jokerCanvas = document.querySelector("#joker-card-canvas");

  function attachScoreCardEffects() {
    if (!dashboard) return;
    dashboard.querySelectorAll(".score-card").forEach((card) => {
      if (card.dataset.effectsReady) return;
      card.dataset.effectsReady = "true";

      card.addEventListener("pointermove", (event) => {
        const rect = card.getBoundingClientRect();
        const px = (event.clientX - rect.left) / rect.width;
        const py = (event.clientY - rect.top) / rect.height;
        const tiltY = (px - 0.5) * 13;
        const tiltX = (0.5 - py) * 11;

        card.style.setProperty("--tilt-x", `${tiltX.toFixed(2)}deg`);
        card.style.setProperty("--tilt-y", `${tiltY.toFixed(2)}deg`);
        card.style.setProperty("--shine", "1");

        const corner =
          px < 0.5 && py < 0.5
            ? "top-left"
            : px >= 0.5 && py < 0.5
              ? "top-right"
              : px < 0.5
                ? "bottom-left"
                : "bottom-right";
        setPeel(card, corner);
      });

      card.addEventListener("pointerleave", () => {
        card.style.setProperty("--tilt-x", "0deg");
        card.style.setProperty("--tilt-y", "0deg");
        card.style.setProperty("--shine", "0");
        card.style.setProperty("--peel", "0");
      });
    });
  }

  function setPeel(card, corner) {
    const settings = {
      "top-left": {
        angle: "315deg",
        path: "0 0, 42px 0, 0 42px",
      },
      "top-right": {
        angle: "225deg",
        path: "100% 0, calc(100% - 42px) 0, 100% 42px",
      },
      "bottom-left": {
        angle: "45deg",
        path: "0 100%, 42px 100%, 0 calc(100% - 42px)",
      },
      "bottom-right": {
        angle: "135deg",
        path: "100% 100%, calc(100% - 42px) 100%, 100% calc(100% - 42px)",
      },
    }[corner];
    card.style.setProperty("--peel-angle", settings.angle);
    card.style.setProperty("--peel-path", settings.path);
    card.style.setProperty("--peel", "0.92");
  }

  function initDashboardObserver() {
    attachScoreCardEffects();
    if (!dashboard) return;
    const observer = new MutationObserver(attachScoreCardEffects);
    observer.observe(dashboard, { childList: true });
  }

  function initDraggableJoker() {
    if (!jokerCard) return;
    let dragging = false;
    let hovering = false;
    let startX = 0;
    let startY = 0;
    let cardX = 0;
    let cardY = 0;

    function readPosition() {
      const rect = jokerCard.getBoundingClientRect();
      cardX = rect.left;
      cardY = rect.top;
      jokerCard.style.setProperty("--card-x", `${cardX}px`);
      jokerCard.style.setProperty("--card-y", `${cardY}px`);
    }

    jokerCard.addEventListener("pointerdown", (event) => {
      readPosition();
      dragging = true;
      startX = event.clientX - cardX;
      startY = event.clientY - cardY;
      jokerCard.classList.add("is-dragging");
      jokerCard.setPointerCapture(event.pointerId);
    });

    jokerCard.addEventListener("pointerenter", () => {
      hovering = true;
      jokerCard.style.setProperty("--card-float-y", "0px");
      jokerCard.style.setProperty("--card-rz", "0deg");
    });

    jokerCard.addEventListener("pointermove", (event) => {
      const rect = jokerCard.getBoundingClientRect();
      const localX = (event.clientX - rect.left) / rect.width;
      const localY = (event.clientY - rect.top) / rect.height;
      jokerCard.style.setProperty("--card-ry", `${((localX - 0.5) * 18).toFixed(2)}deg`);
      jokerCard.style.setProperty("--card-rx", `${((0.5 - localY) * 18).toFixed(2)}deg`);

      if (!dragging) return;
      const maxX = Math.max(0, window.innerWidth - rect.width);
      const maxY = Math.max(0, window.innerHeight - rect.height);
      cardX = Math.min(maxX, Math.max(0, event.clientX - startX));
      cardY = Math.min(maxY, Math.max(0, event.clientY - startY));
      jokerCard.style.setProperty("--card-x", `${cardX}px`);
      jokerCard.style.setProperty("--card-y", `${cardY}px`);
      jokerCard.style.setProperty("--card-rz", `${((event.movementX || 0) * 0.55).toFixed(2)}deg`);
    });

    function release(event) {
      if (!dragging) return;
      dragging = false;
      jokerCard.classList.remove("is-dragging");
      jokerCard.style.setProperty("--card-rx", "0deg");
      jokerCard.style.setProperty("--card-ry", "0deg");
      jokerCard.style.setProperty("--card-rz", "0deg");
      if (jokerCard.hasPointerCapture(event.pointerId)) {
        jokerCard.releasePointerCapture(event.pointerId);
      }
    }

    jokerCard.addEventListener("pointerup", release);
    jokerCard.addEventListener("pointercancel", release);
    jokerCard.addEventListener("pointerleave", () => {
      hovering = false;
      if (dragging) return;
      jokerCard.style.setProperty("--card-rx", "0deg");
      jokerCard.style.setProperty("--card-ry", "0deg");
    });

    function idle(now) {
      if (!hovering && !dragging) {
        const t = now * 0.001;
        const orbit = t * ((Math.PI * 2) / 10);
        const pressX = Math.cos(orbit);
        const pressY = Math.sin(orbit);
        const pressure = 0.7 + 0.3 * Math.sin(t * 2.5);
        const rx = -pressY * 9 * pressure;
        const ry = pressX * 10 * pressure;
        const rz = Math.sin(orbit * 0.5) * 4;
        const floatX = pressX * 2.5;
        const floatY = Math.sin(t * 1.1) * 4 + pressY * 2.5;

        jokerCard.style.setProperty("--card-float-x", `${floatX.toFixed(2)}px`);
        jokerCard.style.setProperty("--card-float-y", `${floatY.toFixed(2)}px`);
        jokerCard.style.setProperty("--card-rx", `${rx.toFixed(2)}deg`);
        jokerCard.style.setProperty("--card-ry", `${ry.toFixed(2)}deg`);
        jokerCard.style.setProperty("--card-rz", `${rz.toFixed(2)}deg`);
      }
      requestAnimationFrame(idle);
    }

    requestAnimationFrame(idle);
  }

  function initJokerCanvas() {
    if (!jokerCanvas) return;
    const context = jokerCanvas.getContext("2d");
    if (!context) return;
    const pixelData = window.JOKER_PIXEL_DATA;
    if (!pixelData) return;

    const sourceCanvas = document.createElement("canvas");
    sourceCanvas.width = pixelData.width;
    sourceCanvas.height = pixelData.height;
    const sourceContext = sourceCanvas.getContext("2d");
    const image = sourceContext.createImageData(pixelData.width, pixelData.height);

    for (let index = 0; index < pixelData.width * pixelData.height; index += 1) {
      const packed = pixelData.packed[Math.floor(index / 8)] || 0;
      const nibble = (packed >> ((index % 8) * 4)) & 0xf;
      const offset = index * 4;
      if (nibble === 0) {
        image.data[offset + 3] = 0;
        continue;
      }
      const color = pixelData.palette[nibble - 1];
      image.data[offset] = color[0];
      image.data[offset + 1] = color[1];
      image.data[offset + 2] = color[2];
      image.data[offset + 3] = 255;
    }
    sourceContext.putImageData(image, 0, 0);

    function resize() {
      const rect = jokerCanvas.getBoundingClientRect();
      const scale = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
      const width = Math.max(1, Math.floor(rect.width * scale));
      const height = Math.max(1, Math.floor(rect.height * scale));
      if (jokerCanvas.width !== width || jokerCanvas.height !== height) {
        jokerCanvas.width = width;
        jokerCanvas.height = height;
      }
      return { width, height };
    }

    function draw() {
      const { width, height } = resize();
      context.imageSmoothingEnabled = false;
      context.clearRect(0, 0, width, height);
      context.drawImage(sourceCanvas, 0, 0, width, height);
    }

    window.addEventListener("resize", draw);
    draw();
  }

  initDashboardObserver();
  initDraggableJoker();
  initJokerCanvas();
})();
