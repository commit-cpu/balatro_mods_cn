(() => {
  const canvas = document.querySelector("#background-shader");
  const toggle = document.querySelector("#background-toggle");
  if (!canvas || !toggle) return;

  const saved = localStorage.getItem("balatro-cn-bg");
  let enabled = saved === null ? true : saved === "on";
  toggle.checked = enabled;

  const gl =
    canvas.getContext("webgl", {
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: "high-performance",
    }) || canvas.getContext("experimental-webgl");
  if (!gl) {
    toggle.checked = false;
    toggle.disabled = true;
    return;
  }

  const vertexSource = `
    attribute vec2 aPosition;
    void main() {
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }
  `;

  const fragmentSource = `
    precision highp float;
    uniform vec3 iResolution;
    uniform float iTime;
    uniform vec2 iCenter;

    #define SPIN_ROTATION -2.0
    #define SPIN_SPEED 7.0
    #define OFFSET vec2(0.0)
    #define COLOUR_1 vec4(0.871, 0.267, 0.231, 1.0)
    #define COLOUR_2 vec4(0.0, 0.42, 0.706, 1.0)
    #define COLOUR_3 vec4(0.086, 0.137, 0.145, 1.0)
    #define CONTRAST 3.5
    #define LIGTHING 0.4
    #define SPIN_AMOUNT 0.25
    #define PIXEL_FILTER 745.0
    #define SPIN_EASE 1.0

    vec4 effect(vec2 screenSize, vec2 screenCoords) {
      float pixelSize = length(screenSize.xy) / PIXEL_FILTER;
      vec2 uv = (floor(screenCoords.xy * (1.0 / pixelSize)) * pixelSize - 0.5 * screenSize.xy) / length(screenSize.xy) - OFFSET;
      vec2 centerUv = (iCenter * screenSize.xy - 0.5 * screenSize.xy) / length(screenSize.xy) - OFFSET;
      vec2 spinUv = uv - centerUv;
      float uvLen = length(spinUv);
      float speed = SPIN_ROTATION * SPIN_EASE * 0.2 + 302.2;
      float angle = atan(spinUv.y, spinUv.x) + speed - SPIN_EASE * 20.0 * (SPIN_AMOUNT * uvLen + (1.0 - SPIN_AMOUNT));
      uv = centerUv + vec2(uvLen * cos(angle), uvLen * sin(angle));
      uv *= 30.0;
      speed = iTime * SPIN_SPEED;
      vec2 uv2 = vec2(uv.x + uv.y);

      for (int i = 0; i < 5; i++) {
        uv2 += sin(max(uv.x, uv.y)) + uv;
        uv += 0.5 * vec2(
          cos(5.1123314 + 0.353 * uv2.y + speed * 0.131121),
          sin(uv2.x - 0.113 * speed)
        );
        uv -= 1.0 * cos(uv.x + uv.y) - 1.0 * sin(uv.x * 0.711 - uv.y);
      }

      float contrastMod = 0.25 * CONTRAST + 0.5 * SPIN_AMOUNT + 1.2;
      float paintRes = min(2.0, max(0.0, length(uv) * 0.035 * contrastMod));
      float c1p = max(0.0, 1.0 - contrastMod * abs(1.0 - paintRes));
      float c2p = max(0.0, 1.0 - contrastMod * abs(paintRes));
      float c3p = 1.0 - min(1.0, c1p + c2p);
      float light = (LIGTHING - 0.2) * max(c1p * 5.0 - 4.0, 0.0) + LIGTHING * max(c2p * 5.0 - 4.0, 0.0);
      return (0.3 / CONTRAST) * COLOUR_1
        + (1.0 - 0.3 / CONTRAST) * (COLOUR_1 * c1p + COLOUR_2 * c2p + vec4(c3p * COLOUR_3.rgb, c3p * COLOUR_1.a))
        + light;
    }

    void main() {
      vec4 color = effect(iResolution.xy, gl_FragCoord.xy);
      color.rgb *= 0.78;
      gl_FragColor = color;
    }
  `;

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) || "Shader compile failed");
    }
    return shader;
  }

  let program;
  try {
    program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "Shader link failed");
    }
  } catch (error) {
    console.error(error);
    toggle.checked = false;
    toggle.disabled = true;
    return;
  }

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  const positionLocation = gl.getAttribLocation(program, "aPosition");
  const resolutionLocation = gl.getUniformLocation(program, "iResolution");
  const timeLocation = gl.getUniformLocation(program, "iTime");
  const centerLocation = gl.getUniformLocation(program, "iCenter");
  const start = performance.now();
  let lastFrameTime = start;
  let frame = 0;
  const center = { x: 0.5, y: 0.5 };
  const targetCenter = { x: 0.5, y: 0.5 };

  function clamp01(value) {
    return Math.max(0, Math.min(1, value));
  }

  function setTargetCenterFromPointer(event) {
    if (!enabled) return;
    targetCenter.x = clamp01(event.clientX / Math.max(1, window.innerWidth));
    targetCenter.y = clamp01(1 - event.clientY / Math.max(1, window.innerHeight));
  }

  function resetTargetCenter() {
    targetCenter.x = 0.5;
    targetCenter.y = 0.5;
  }

  function easeCenter(now) {
    const deltaSeconds = Math.min(0.1, Math.max(0, (now - lastFrameTime) / 1000));
    lastFrameTime = now;
    const t = 1 - Math.exp(-deltaSeconds * 0.013);
    center.x += (targetCenter.x - center.x) * t;
    center.y += (targetCenter.y - center.y) * t;
  }

  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    const width = Math.max(1, Math.floor(window.innerWidth * ratio));
    const height = Math.max(1, Math.floor(window.innerHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    }
  }

  function draw(now) {
    cancelAnimationFrame(frame);
    const visible = enabled;
    document.body.classList.toggle("shader-visible", visible);
    if (!visible || document.visibilityState !== "visible") return;

    resize();
    easeCenter(now);
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.enableVertexAttribArray(positionLocation);
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
    gl.uniform3f(resolutionLocation, canvas.width, canvas.height, 1);
    gl.uniform1f(timeLocation, (now - start) / 1000);
    gl.uniform2f(centerLocation, center.x, center.y);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    frame = requestAnimationFrame(draw);
  }

  window.BalatroBackground = {
    refresh() {
      draw(performance.now());
    },
  };

  toggle.addEventListener("change", () => {
    enabled = toggle.checked;
    localStorage.setItem("balatro-cn-bg", enabled ? "on" : "off");
    draw(performance.now());
  });

  window.addEventListener("resize", () => draw(performance.now()));
  window.addEventListener("pointermove", setTargetCenterFromPointer, { passive: true });
  window.addEventListener("pointerleave", resetTargetCenter);
  window.addEventListener("blur", resetTargetCenter);
  document.addEventListener("visibilitychange", () => draw(performance.now()));
  draw(performance.now());
})();
