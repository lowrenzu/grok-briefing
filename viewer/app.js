(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const canvas = $("#galaxy");
  const stage = $("#galaxyStage");
  const context = canvas.getContext("2d", { alpha: true });
  const nodesEl = $("#noteCount");
  const linksEl = $("#linkCount");
  const messagesEl = $("#chatMessages");
  const questionInput = $("#questionInput");
  const sendButton = $("#sendButton");
  const micButton = $("#micButton");
  const thinkingLine = $("#thinkingLine");
  const graphStatus = $("#graphStatus");
  const sourceEmpty = $("#sourceEmpty");
  const sourceContent = $("#sourceContent");
  const helpDialog = $("#helpDialog");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const core = $("#jarvisCore");

  let graph = window.JARVIS_GRAPH && Array.isArray(window.JARVIS_GRAPH.nodes)
    ? window.JARVIS_GRAPH
    : { nodes: [], links: [] };
  let width = 0;
  let height = 0;
  let pixelRatio = 1;
  let rotationX = 0.11;
  let rotationY = 0;
  let targetRotation = null;
  let zoom = 1;
  let targetZoom = 1;
  let dragging = false;
  let pointerStart = null;
  let hoveredId = null;
  let selectedId = null;
  let activeGroup = null;
  let searchTerm = "";
  let focusedIds = new Set();
  let labelIds = new Set();
  let textIds = new Set();
  let clusterIds = [];
  let graphOverview = false;
  let busy = false;
  let lastWeatherData = null;
  let voiceEnabled = false;
  let speechToken = 0;
  let recognition = null;
  let voiceBooted = false;
  let boundaryCount = 0;
  let boundaryTimer = null;
  let speechFallback = null;
  let speechWatchdog = null;
  let stars = [];
  let projectedNodes = [];
  let lastFrameTime = performance.now();
  // Position écran interpolée de chaque point : c'est ce qui rend les transitions fluides.
  const motion = new Map();
  // Couronne de notes : son rayon se déduit du cœur mesuré à l'écran, pour que les
  // notes restent juste autour de JARVIS au lieu de partir vers les bords de la scène.
  const orbit = { cx: 0, cy: 0, rx: 0, ry: 0, inner: 0, tilt: .84 };
  // Niveau de lecture : « main » = notes principales, « detail » = notes spécifiques.
  let level = "themes";
  let themeFilter = null;
  let focusId = null;
  const pulseTimes = new Map();

  const palette = ["#75e3df", "#83aaff", "#ce98f4", "#e9b97a", "#ef8cac", "#83d2a1", "#70b8d5", "#d5d979"];
  const colors = new Map();
  const colorForGroup = (group) => {
    if (group === "Mes notes") return "#72e4ef";
    if (!colors.has(group)) {
      let hash = 0;
      for (const character of group) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
      colors.set(group, palette[Math.abs(hash) % palette.length]);
    }
    return colors.get(group);
  };

  function normalize(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("fr-FR");
  }

  function createStars() {
    let seed = 87421;
    const random = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
    stars = Array.from({ length: 170 }, () => ({
      x: random(),
      y: random(),
      size: .35 + random() * 1.2,
      alpha: .12 + random() * .5,
      phase: random() * Math.PI * 2,
    }));
  }

  function resizeCanvas() {
    const rect = stage.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    width = rect.width;
    height = rect.height;
    pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    measureOrbit(rect);
  }

  function measureOrbit(stageRect) {
    const base = Math.min(width, height);
    let heart = base * .275;
    const coreRect = core ? core.getBoundingClientRect() : null;
    if (coreRect && coreRect.width > 0) {
      orbit.cx = coreRect.left - stageRect.left + coreRect.width / 2;
      orbit.cy = coreRect.top - stageRect.top + coreRect.height / 2;
      heart = coreRect.width / 2;
    } else {
      orbit.cx = width / 2;
      orbit.cy = height * .47;
    }
    // Les thèmes et les notes occupent le même cercle, autour du logement. Plus de
    // colonnes latérales : le cercle peut donc être presque rond.
    orbit.inner = heart + Math.max(12, base * .028);
    orbit.rx = Math.max(heart + 22, Math.min(heart + base * .12, width / 2 - 34));
    orbit.ry = Math.max(heart + 26, Math.min(heart + base * .12, height / 2 - 40));
  }

  function neighborsOf(id) {
    const result = new Set();
    for (const link of graph.links) {
      const source = typeof link.source === "object" ? link.source.id : link.source;
      const target = typeof link.target === "object" ? link.target.id : link.target;
      if (source === id) result.add(target);
      else if (target === id) result.add(source);
    }
    return result;
  }

  function orbitPoint(index, total) {
    const viewScale = Math.min(1.08, Math.max(1, zoom));
    const angle = (index / Math.max(total, 1)) * Math.PI * 2 - Math.PI / 2 + rotationY;
    // Inclinaison : le glissement vertical la règle, et une respiration très lente
    // l'anime au repos pour que le cercle paraisse vivant, comme un hologramme.
    const tilt = orbit.tilt;
    const offsetX = Math.cos(angle) * orbit.rx * viewScale;
    const offsetY = Math.sin(angle) * orbit.ry * tilt * viewScale;
    const depth = (Math.sin(angle) + 1) / 2;
    return {
      x: orbit.cx + offsetX,
      y: orbit.cy + offsetY,
      z: Math.sin(angle),
      factor: .74 + depth * .38,
      radius: Math.hypot(offsetX, offsetY),
    };
  }

  // Deux niveaux de lecture : les notes principales autour de JARVIS, puis les notes
  // spécifiques d'une note principale dès qu'on clique dessus.
  const THEME_PROMPTS = {
    "PÊCHE": "Quelles informations sur la pêche ai-je enregistrées ?",
    "PROJETS": "Quels sont mes projets et prochaines étapes ?",
    "CRÉATIVITÉ": "Quelles idées créatives ai-je déjà notées ?",
    "MÉDIAS": "Quelles idées de contenus ou de médias ai-je notées ?",
    "FORMATION": "Qu’est-ce que je veux apprendre ou améliorer ?",
    "ANALYSE": "Quelles analyses ou décisions ai-je consignées ?",
    "NATURE": "Quelles notes ai-je sur la nature et les sorties ?",
    "QUOTIDIEN": "Quelles tâches ou rappels ai-je notés ?",
  };

  // Les thèmes sont le premier cercle : ils se présentent exactement comme les notes.
  function themeList() {
    if (Array.isArray(graph.themes) && graph.themes.length) return graph.themes;
    const counts = new Map();
    for (const node of graph.nodes) {
      const label = node.theme || "MES NOTES";
      counts.set(label, (counts.get(label) || 0) + 1);
    }
    return Array.from(counts, ([label, count]) => ({ label, count }));
  }

  function themeNodes() {
    return themeList().map((theme) => ({
      id: `theme:${theme.label}`,
      label: theme.label,
      theme: theme.label,
      count: theme.count,
      excerpt: `${theme.count} note${theme.count > 1 ? "s" : ""}`,
      connections: theme.count,
      isTheme: true,
    }));
  }

  function notesOfTheme(label) {
    return graph.nodes.filter((node) => (node.theme || "MES NOTES") === label);
  }

  function mainNotes() {
    const ranked = [...graph.nodes].sort((a, b) => (b.connections || 0) - (a.connections || 0));
    return ranked.slice(0, Math.min(8, ranked.length));
  }

  function visibleNodes() {
    if (searchTerm) {
      const matches = graph.nodes.filter((node) => normalize(`${node.label} ${node.excerpt}`).includes(searchTerm));
      if (matches.length) return matches;
    }
    if (graphOverview) return [...graph.nodes];
    if (level === "detail" && focusId !== null) {
      const hub = graph.nodes.find((node) => node.id === focusId);
      const related = graph.nodes.filter((node) => node.id !== focusId && neighborsOf(focusId).has(node.id));
      return hub ? [hub, ...related] : [...graph.nodes];
    }
    if (level === "main") {
      // Second cercle : toutes les notes du thème choisi.
      if (themeFilter !== null) return notesOfTheme(themeFilter);
      return mainNotes();
    }
    return [];
  }

  function linkIds(link) {
    return {
      source: typeof link.source === "object" ? link.source.id : link.source,
      target: typeof link.target === "object" ? link.target.id : link.target,
    };
  }

  function draw() {
    if (!width || !height) return;
    context.clearRect(0, 0, width, height);
    const time = performance.now() / 1000;
    // Respiration de l'inclinaison : ±3 % sur environ 18 secondes.
    orbit.tilt = (.62 + .38 * Math.abs(Math.cos(rotationX))) * (1 + Math.sin(time * .35) * .03);

    for (const star of stars) {
      const twinkle = .65 + .35 * Math.sin(time * .8 + star.phase);
      const starX = star.x * width;
      const starY = star.y * height;
      const fromCenter = Math.hypot(starX - orbit.cx, starY - orbit.cy);
      const avatarClear = orbit.inner * .86;
      const fade = Math.max(.08, Math.min(1, (fromCenter - avatarClear) / (Math.min(width, height) * .1)));
      context.globalAlpha = star.alpha * twinkle * fade;
      context.fillStyle = "#d9f5fb";
      context.beginPath();
      context.arc(starX, starY, star.size, 0, Math.PI * 2);
      context.fill();
    }
    context.globalAlpha = 1;

    const centerGlow = context.createRadialGradient(orbit.cx, orbit.cy, 4, orbit.cx, orbit.cy, Math.min(width, height) * .43);
    centerGlow.addColorStop(0, "rgba(55, 143, 160, .045)");
    centerGlow.addColorStop(.5, "rgba(31, 73, 91, .02)");
    centerGlow.addColorStop(1, "rgba(9, 17, 27, 0)");
    context.fillStyle = centerGlow;
    context.fillRect(0, 0, width, height);

    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    const showingThemes = level === "themes" && !searchTerm && !graphOverview;
    const displayed = showingThemes ? themeNodes() : visibleNodes();
    const count = displayed.length;
    const activeIds = new Set(focusedIds);
    if (selectedId !== null) {
      activeIds.add(selectedId);
      for (const id of neighborsOf(selectedId)) activeIds.add(id);
    }
    if (clusterIds.length) clusterIds.forEach((id) => activeIds.add(id));

    // --- Cible de chaque point, puis interpolation : les notes glissent au lieu de sauter.
    const targets = new Map();
    displayed.forEach((node, index) => targets.set(node.id, orbitPoint(index, count)));
    const now = performance.now();
    const dt = Math.min(.05, Math.max(.001, (now - lastFrameTime) / 1000));
    lastFrameTime = now;
    const ease = 1 - Math.exp(-dt * 9);

    for (const id of Array.from(motion.keys())) {
      if (!targets.has(id)) motion.delete(id);
    }
    const points = new Map();
    for (const [id, target] of targets) {
      let state = motion.get(id);
      if (!state) {
        // Une nouvelle note naît au cœur de JARVIS et s'éloigne en douceur.
        state = { x: orbit.cx, y: orbit.cy, alpha: 0, scale: .35, phase: Math.random() * Math.PI * 2 };
        motion.set(id, state);
      }
      const float = Math.sin(time * .55 + state.phase) * 2.2;
      state.x += (target.x - state.x) * ease;
      state.y += (target.y + float * .35 - state.y) * ease;
      state.alpha += (1 - state.alpha) * ease;
      const hovered = hoveredId === id;
      const wanted = (hovered ? 1.3 : 1) * (target.factor);
      state.scale += (wanted - state.scale) * ease;
      points.set(id, { x: state.x, y: state.y, z: target.z, factor: target.factor, alpha: state.alpha, scale: state.scale });
    }
    const displayedIds = new Set(displayed.map((node) => node.id));

    drawOrbitGuides(time, showingThemes);

    // --- Liens : arcs concentriques avec un flux lumineux qui circule.
    let drawnFocusEdges = 0;
    const focusEdgeLimit = labelIds.size >= 4 ? 18 : 12;
    if (!showingThemes) {
      for (const link of graph.links) {
        const { source, target } = linkIds(link);
        if (!displayedIds.has(source) || !displayedIds.has(target)) continue;
        const relevantEdge = labelIds.has(source) || labelIds.has(target) || source === hoveredId || target === hoveredId;
        if (!graphOverview && activeGroup === null && !relevantEdge) continue;
        if (!graphOverview && activeGroup === null && drawnFocusEdges >= focusEdgeLimit) continue;
        if (!graphOverview && activeGroup === null) drawnFocusEdges += 1;
        const a = points.get(source);
        const b = points.get(target);
        if (!a || !b) continue;
        const bright = labelIds.has(source) && labelIds.has(target) || labelIds.size <= 1 && (source === selectedId || target === selectedId);
        const centerX = orbit.cx;
        const centerY = orbit.cy;
        const startAngle = Math.atan2(a.y - centerY, a.x - centerX);
        const endAngle = Math.atan2(b.y - centerY, b.x - centerX);
        let angleDelta = endAngle - startAngle;
        while (angleDelta > Math.PI) angleDelta -= Math.PI * 2;
        while (angleDelta < -Math.PI) angleDelta += Math.PI * 2;
        const arcRadius = (Math.hypot(a.x - centerX, a.y - centerY) + Math.hypot(b.x - centerX, b.y - centerY)) / 2;
        context.save();
        context.beginPath();
        context.arc(centerX, centerY, arcRadius, startAngle, startAngle + angleDelta, angleDelta < 0);
        context.lineWidth = bright ? 1.3 : .7;
        context.strokeStyle = bright ? "rgba(120, 236, 240, .5)" : "rgba(107, 196, 217, .16)";
        context.globalAlpha = Math.min(a.alpha, b.alpha) * (bright ? .9 : .55);
        context.stroke();
        // Le flux lumineux qui parcourt l'arc rend le réseau lisible et vivant.
        context.setLineDash([2, 26]);
        context.lineDashOffset = -time * 46;
        context.lineWidth = 1.7;
        context.strokeStyle = bright ? "rgba(196, 252, 255, .9)" : "rgba(150, 232, 245, .38)";
        context.stroke();
        context.restore();
      }
    }
    context.globalAlpha = 1;
    context.setLineDash([]);

    // --- Points et libellés, du plus lointain au plus proche.
    const ordered = displayed.map((node) => ({ node, point: points.get(node.id) }))
      .filter((item) => item.point)
      .sort((a, b) => a.point.z - b.point.z);
    projectedNodes = ordered;

    for (const { node, point } of ordered) {
      const isHovered = hoveredId === node.id;
      if (showingThemes) {
        drawThemeNode(node, point, isHovered);
        continue;
      }
      const isSelected = selectedId === node.id;
      const isFocusNode = level === "detail" && node.id === focusId;
      const isSourceNode = labelIds.has(node.id);
      const inTheme = level === "main" && !searchTerm && !graphOverview;
      const radius = nodeRadius(node, point, isSelected, isHovered);
      const color = colorForGroup(node.theme || node.group || "notes");
      const pulseStart = pulseTimes.get(node.id);
      const age = pulseStart ? (now - pulseStart) / 1000 : 9;
      if (age < 2.2) {
        const pulse = age / 2.2;
        context.beginPath();
        context.arc(point.x, point.y, radius + pulse * 26, 0, Math.PI * 2);
        context.strokeStyle = color;
        context.globalAlpha = (1 - pulse) * .7 * point.alpha;
        context.lineWidth = 1.4;
        context.stroke();
        context.globalAlpha = 1;
      }
      const emphasis = isSelected || isHovered || isFocusNode;
      const baseAlpha = emphasis ? .98 : inTheme || level === "detail" ? .9 : graphOverview ? .55 : .2;
      drawPill(point.x, point.y, radius, point.alpha * baseAlpha, emphasis ? 1.15 : 1, radius * (emphasis ? 2.05 : 1.62));

      const labelAlpha = point.alpha * (emphasis ? 1 : inTheme || level === "detail" ? .96 : .45);
      const shouldLabel = emphasis || labelIds.has(node.id) || inTheme
        || (level === "detail" && (ordered.length <= 14 || point.z > .15));
      if (shouldLabel && labelAlpha > .05) {
        placeLabel(node.label, point, radius, labelAlpha, emphasis);
      }
    }
    context.globalAlpha = 1;
  }

  // --- Briques de dessin -----------------------------------------------------

  function nodeRadius(node, point, isSelected, isHovered) {
    const base = Math.max(3.4, Math.min(7.2, 4.4 + (node.connections || 0) * .16));
    return base * (isSelected ? 1.35 : isHovered ? 1.22 : 1) * (point.scale || 1) * (1 + Math.sin(performance.now() / 620 + (node.id % 7)) * .05);
  }

  function drawPill(x, y, radius, alpha, glow, ringRadius) {
    if (alpha <= .01) return;
    context.save();
    const halo = context.createRadialGradient(x, y, radius * .4, x, y, radius * 4.6);
    halo.addColorStop(0, `rgba(150,244,252,${Math.min(.55, .5 * alpha * glow)})`);
    halo.addColorStop(.45, `rgba(96,216,236,${.16 * alpha})`);
    halo.addColorStop(1, "rgba(96,216,236,0)");
    context.fillStyle = halo;
    context.beginPath();
    context.arc(x, y, radius * 4.6, 0, Math.PI * 2);
    context.fill();
    context.globalAlpha = alpha;
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fillStyle = "#d8feff";
    context.fill();
    context.beginPath();
    context.arc(x, y, radius * .52, 0, Math.PI * 2);
    context.fillStyle = "rgba(255,255,255,.9)";
    context.fill();
    context.beginPath();
    context.arc(x, y, ringRadius, 0, Math.PI * 2);
    context.strokeStyle = `rgba(126,232,244,${.5 * alpha})`;
    context.lineWidth = 1;
    context.stroke();
    context.beginPath();
    context.arc(x, y, ringRadius * 1.45, 0, Math.PI * 2);
    context.strokeStyle = `rgba(126,232,244,${.16 * alpha})`;
    context.stroke();
    context.restore();
  }

  function placeLabel(text, point, radius, alpha, emphasis) {
    const radialX = point.x - orbit.cx;
    const radialY = point.y - orbit.cy;
    const length = Math.hypot(radialX, radialY) || 1;
    const outwardX = radialX / length;
    const outwardY = radialY / length;
    context.save();
    context.globalAlpha = alpha;
    context.font = `${emphasis ? 13 : 12}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    context.textBaseline = "middle";
    context.shadowColor = "rgba(0, 0, 0, .98)";
    context.shadowBlur = 7;
    context.fillStyle = emphasis ? "#f6ffff" : "#dcf3f8";
    const label = text.length > 24 ? `${text.slice(0, 22)}…` : text;
    const maxWidth = Math.min(196, Math.max(124, width * .3));
    const offset = radius + 12;
    const side = Math.abs(outwardX) > .72;
    context.textAlign = side ? "center" : outwardX > .25 ? "left" : outwardX < -.25 ? "right" : "center";
    let labelX = point.x + (side ? 0 : outwardX * offset);
    let labelY = side ? point.y + (outwardY < 0 ? -offset : offset) : point.y + outwardY * offset;
    const half = context.textAlign === "center" ? maxWidth / 2 : 0;
    const leftBound = context.textAlign === "right" ? maxWidth : half;
    const rightBound = context.textAlign === "left" ? maxWidth : half;
    labelX = Math.max(8 + leftBound, Math.min(width - 8 - rightBound, labelX));
    labelY = Math.max(14, Math.min(height - 12, labelY));
    context.lineWidth = 3;
    context.strokeStyle = "rgba(2, 10, 16, .82)";
    context.strokeText(label, labelX, labelY, maxWidth);
    context.fillText(label, labelX, labelY, maxWidth);
    context.restore();
  }

  function drawThemeNode(node, point, isHovered) {
    const empty = !node.count;
    const radius = 8.6 * (point.scale || 1) * (empty ? .78 : 1);
    const alpha = point.alpha * (empty ? .38 : isHovered ? 1 : .95);
    drawPill(point.x, point.y, radius, alpha, isHovered ? 1.5 : 1, point.alpha * radius * 1.9);
    context.save();
    context.globalAlpha = point.alpha * (empty ? .45 : isHovered ? 1 : .92);
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.shadowColor = "rgba(0,0,0,.95)";
    context.shadowBlur = 7;
    context.lineWidth = 3;
    context.strokeStyle = "rgba(2,10,16,.85)";
    context.font = `600 ${isHovered ? 15 : 14}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    context.fillStyle = isHovered ? "#ffffff" : "#e6fbff";
    const labelY = point.y + radius * 2.6 + 13;
    context.strokeText(node.label, point.x, labelY, 196);
    context.fillText(node.label, point.x, labelY, 196);
    context.font = `11px ui-monospace, SFMono-Regular, Menlo, monospace`;
    context.globalAlpha = point.alpha * (empty ? .35 : .72);
    context.fillStyle = "#bfe6ef";
    const countText = node.count ? `${node.count} note${node.count > 1 ? "s" : ""}` : "aucune note";
    context.strokeText(countText, point.x, labelY + 17, 150);
    context.fillText(countText, point.x, labelY + 17, 150);
    context.restore();
  }

  // Anneau de guidage : ellipse pointillée qui tourne, graduations et halo tournant.
  function drawOrbitGuides(time, showingThemes) {
    const { cx, cy, rx, ry } = orbit;
    const tilt = orbit.tilt;
    context.save();
    context.beginPath();
    context.ellipse(cx, cy, rx, ry * tilt, 0, 0, Math.PI * 2);
    context.strokeStyle = "rgba(94, 196, 220, .12)";
    context.lineWidth = 1;
    context.stroke();
    // Graduations : le côté « instrument » du HUD.
    const ticks = 72;
    for (let index = 0; index < ticks; index += 1) {
      const angle = (index / ticks) * Math.PI * 2;
      const long = index % 6 === 0;
      const inner = 1 - (long ? .035 : .018);
      const x1 = cx + Math.cos(angle) * rx * inner;
      const y1 = cy + Math.sin(angle) * ry * tilt * inner;
      const x2 = cx + Math.cos(angle) * rx;
      const y2 = cy + Math.sin(angle) * ry * tilt;
      context.beginPath();
      context.moveTo(x1, y1);
      context.lineTo(x2, y2);
      context.strokeStyle = long ? "rgba(126,232,244,.22)" : "rgba(126,232,244,.1)";
      context.stroke();
    }
    // Deux arcs lumineux en rotation : le cercle « respire » en permanence.
    for (const [offset, span, alpha, speed] of [[0, .55, .3, .07], [Math.PI, .3, .16, -.045]]) {
      const start = time * speed + offset;
      context.beginPath();
      context.ellipse(cx, cy, rx, ry * tilt, 0, start, start + span);
      context.strokeStyle = `rgba(150, 240, 250, ${alpha})`;
      context.lineWidth = 1.6;
      context.stroke();
    }
    if (showingThemes) {
      const breathe = 1 + Math.sin(time * .8) * .012;
      context.beginPath();
      context.ellipse(cx, cy, rx * breathe, ry * tilt * breathe, 0, 0, Math.PI * 2);
      context.strokeStyle = "rgba(126,232,244,.07)";
      context.lineWidth = 10;
      context.stroke();
    }
    context.restore();
  }

  function frame() {
    if (targetRotation) {
      const deltaY = Math.atan2(Math.sin(targetRotation.y - rotationY), Math.cos(targetRotation.y - rotationY));
      rotationY += deltaY * .075;
      rotationX += (targetRotation.x - rotationX) * .075;
      targetZoom += (targetRotation.zoom - targetZoom) * .1;
      if (Math.abs(deltaY) < .001 && Math.abs(targetRotation.x - rotationX) < .001) {
        rotationY = targetRotation.y;
        rotationX = targetRotation.x;
        targetRotation = null;
      }
    } else if (!dragging && !reducedMotion) {
      rotationY += .00016;
    }
    if (!targetRotation && Math.abs(zoom - targetZoom) > .001) zoom += (targetZoom - zoom) * .12;
    draw();
    window.requestAnimationFrame(frame);
  }

  function pointFromEvent(event) {
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function pickNode(x, y) {
    let nearest = null;
    let min = Infinity;
    for (const item of projectedNodes) {
      const dx = item.point.x - x;
      const dy = item.point.y - y;
      const distance = Math.hypot(dx, dy);
      const radius = Math.max(12, 7 + (item.node.connections || 0) * .3);
      if (distance < radius && distance < min) {
        nearest = item.node;
        min = distance;
      }
    }
    return nearest;
  }

  function angleOfIndex(index, total) {
    return (index / Math.max(total, 1)) * Math.PI * 2 - Math.PI / 2;
  }

  function cameraTo(id, extraZoom = 1.14) {
    const list = visibleNodes();
    const index = list.findIndex((node) => node.id === id);
    if (index < 0) return;
    // L'anneau ne se « retourne » plus : on le fait tourner pour placer la note choisie
    // en bas de l'orbite, là où rien ne la masque.
    targetRotation = { x: rotationX, y: Math.PI / 2 - angleOfIndex(index, list.length), zoom: extraZoom };
  }

  function cameraToCluster(ids) {
    const list = visibleNodes();
    const indexes = ids.map((id) => list.findIndex((node) => node.id === id)).filter((index) => index >= 0);
    if (!indexes.length) return;
    let sumX = 0;
    let sumY = 0;
    for (const index of indexes) {
      const angle = angleOfIndex(index, list.length);
      sumX += Math.cos(angle);
      sumY += Math.sin(angle);
    }
    targetRotation = { x: rotationX, y: Math.PI / 2 - Math.atan2(sumY, sumX), zoom: indexes.length > 7 ? 1.04 : 1.08 };
  }

  function appendElement(parent, tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    parent.append(element);
    return element;
  }

  function renderSourcePanel(node, groupIds = []) {
    sourceEmpty.hidden = true;
    sourceContent.hidden = false;
    sourceContent.replaceChildren();

    const isCluster = groupIds.length >= 4;
    const top = appendElement(sourceContent, "div", "source-top");
    const heading = appendElement(top, "div", "source-heading");
    const kicker = appendElement(heading, "div", "source-kicker");
    const kickerDot = document.createElement("i");
    kickerDot.style.background = colorForGroup(node.group || "notes");
    kicker.append(kickerDot, document.createTextNode(isCluster ? `GROUPE DE SOURCES · ${groupIds.length} NOTES` : `${node.group || "MES NOTES"} · SOURCE ${String(node.id + 1).padStart(2, "0")}`));
    appendElement(heading, "h3", "source-title", isCluster ? "Les notes derrière cette réponse" : node.label);
    const excerpt = isCluster
      ? `JARVIS a utilisé plusieurs notes reliées pour construire sa réponse. Ouvrez chaque source pour en vérifier le détail.`
      : (node.excerpt || "Cette note ne contient pas encore d’extrait lisible.");
    appendElement(sourceContent, "p", "source-excerpt", excerpt);

    if (isCluster) {
      const list = appendElement(sourceContent, "div", "cluster-list");
      for (const id of groupIds) {
        const source = graph.nodes.find((item) => item.id === id);
        if (!source) continue;
        const button = appendElement(list, "button", "related-button", source.label);
        button.type = "button";
        button.addEventListener("click", () => selectNode(source.id));
      }
    } else {
      const related = Array.from(neighborsOf(node.id)).slice(0, 5);
      if (related.length) {
        const row = appendElement(sourceContent, "div", "source-related");
        appendElement(row, "span", "source-related-label", "LIÉ À");
        for (const id of related) {
          const neighbor = graph.nodes.find((item) => item.id === id);
          if (!neighbor) continue;
          const button = appendElement(row, "button", "related-button", neighbor.label);
          button.type = "button";
          button.addEventListener("click", () => selectNode(id));
        }
      }
    }
  }

  // Second cercle : les notes du thème choisi, présentées comme les thèmes eux-mêmes.
  function openTheme(label) {
    level = "main";
    themeFilter = label;
    focusId = null;
    selectedId = null;
    graphOverview = false;
    clusterIds = [];
    const notes = notesOfTheme(label);
    focusedIds = new Set(notes.map((node) => node.id));
    labelIds.clear();
    textIds.clear();
    syncGraphToggle();
    sourceContent.hidden = true;
    sourceEmpty.hidden = false;
    $("#sectorLabel").textContent = label;
    updateStageHint(notes.length
      ? `${label} · ${notes.length} NOTE${notes.length > 1 ? "S" : ""} · CLIQUEZ SUR UNE NOTE POUR LA LIRE`
      : `${label} · AUCUNE NOTE POUR L’INSTANT`, "THÈMES");
    graphStatus.textContent = notes.length
      ? `${label} · ${notes.length} note${notes.length > 1 ? "s" : ""}`
      : `${label} · aucune note pour l’instant`;
    renderLegend();
    draw();
  }

  // Ouvre le second niveau : les notes spécifiques liées à une note principale.
  function openDetail(id) {
    const node = graph.nodes.find((item) => item.id === id);
    if (!node) return;
    level = "detail";
    focusId = id;
    selectedId = id;
    graphOverview = false;
    clusterIds = [];
    labelIds = new Set([id]);
    textIds = new Set([id]);
    focusedIds = new Set([id, ...neighborsOf(id)]);
    syncGraphToggle();
    renderSourcePanel(node, []);
    const count = Math.max(0, visibleNodes().length - 1);
    updateStageHint(`${node.label.toUpperCase()} · CLIQUEZ SUR UNE NOTE LIÉE POUR LA LIRE`, (themeFilter || "THÈMES").toUpperCase());
    graphStatus.textContent = `${node.label} · ${count} note${count > 1 ? "s" : ""} liée${count > 1 ? "s" : ""}`;
    draw();
  }

  function backToMain() {
    // Retour au premier cercle : les thèmes.
    level = "themes";
    themeFilter = null;
    focusId = null;
    selectedId = null;
    graphOverview = false;
    clusterIds = [];
    focusedIds.clear();
    labelIds.clear();
    textIds.clear();
    syncGraphToggle();
    sourceContent.hidden = true;
    sourceEmpty.hidden = false;
    $("#sectorLabel").textContent = "TOUS LES THÈMES";
    updateStageHint("VOS NOTES, CLASSÉES PAR THÈME · CLIQUEZ SUR UN POINT POUR OUVRIR SES NOTES");
    graphStatus.textContent = "Index local prêt";
    renderLegend();
    draw();
  }

  function selectNode(id, options = {}) {
    if (typeof id === "string" && id.startsWith("theme:")) {
      openTheme(id.slice(6));
      return;
    }
    const node = graph.nodes.find((item) => item.id === id);
    if (!node) return;
    // Premier niveau : un clic ouvre les notes spécifiques. Second niveau : un clic sur
    // la note principale refermée ramène à la vue d'ensemble.
    if (level === "main" && !searchTerm && !graphOverview) {
      openDetail(id);
      return;
    }
    if (level === "detail" && id === focusId) {
      // Refermer une note ramène à son thème, pas directement à l'accueil.
      if (themeFilter) openTheme(themeFilter);
      else backToMain();
      return;
    }
    selectedId = id;
    graphOverview = false;
    labelIds = new Set([id]);
    textIds = new Set([id]);
    clusterIds = Array.isArray(options.clusterIds) ? options.clusterIds : [];
    focusedIds = new Set([id, ...neighborsOf(id), ...clusterIds]);
    syncGraphToggle();
    renderSourcePanel(node, clusterIds);
    if (options.camera !== false) cameraTo(id);
    if (options.clusterCamera) cameraToCluster(clusterIds);
    updateStageHint("SOURCE EN ORBITE · CLIQUEZ SUR UNE AUTRE ÉTOILE POUR EXPLORER");
    draw();
  }

  function focusSources(ids) {
    const valid = Array.from(new Set(ids)).filter((id) => graph.nodes.some((node) => node.id === id));
    if (!valid.length) return;
    const first = graph.nodes.find((node) => node.id === valid[0]);
    clusterIds = valid.length >= 4 ? valid : [];
    // Une réponse de JARVIS ouvre directement le second niveau sur la note citée.
    level = "detail";
    focusId = first.id;
    selectedId = first.id;
    graphOverview = false;
    labelIds = new Set(valid);
    textIds = new Set(valid.slice(0, 4));
    focusedIds = new Set(valid);
    for (const id of valid) for (const neighbor of neighborsOf(id)) focusedIds.add(neighbor);
    syncGraphToggle();
    renderSourcePanel(first, clusterIds);
    if (valid.length >= 4) cameraToCluster(valid);
    else cameraTo(first.id, valid.length > 1 ? 1.1 : 1.27);
    updateStageHint(valid.length >= 4 ? `CONSTELLATION EN ORBITE · ${valid.length} SOURCES` : "SOURCE EN ORBITE · LE VISAGE DE JARVIS RESTE DÉGAGÉ");
    draw();
  }

  function updateStageHint(text, back = null) {
    const textEl = $("#stageHintText");
    if (textEl) textEl.textContent = text;
    const backButton = $("#hintBack");
    if (!backButton) return;
    // Le bouton retour dit toujours vers quoi il ramène.
    backButton.hidden = !back;
    if (back) {
      const label = $("#hintBackLabel");
      if (label) label.textContent = back;
    }
  }

  function syncGraphToggle() {
    const button = $("#toggleGraph");
    if (!button) return;
    button.setAttribute("aria-pressed", String(graphOverview));
    button.setAttribute("aria-label", graphOverview ? "Masquer le graphe des notes" : "Afficher le graphe des notes");
    button.title = graphOverview ? "Masquer le graphe des notes" : "Afficher le graphe des notes";
  }

  function toggleGraphOverview() {
    graphOverview = !graphOverview;
    if (graphOverview) {
      level = "themes";
      themeFilter = null;
      focusId = null;
      selectedId = null;
      focusedIds.clear();
      labelIds.clear();
      textIds.clear();
      clusterIds = [];
      updateStageHint("CONSTELLATION EN ORBITE · CLIQUEZ SUR UNE ÉTOILE POUR L’EXPLORER");
      graphStatus.textContent = "Vue du graphe de notes";
    } else {
      selectedId = null;
      focusedIds.clear();
      labelIds.clear();
      textIds.clear();
      clusterIds = [];
      updateStageHint("NOTES PRINCIPALES · CLIQUEZ SUR UNE NOTE POUR VOIR SES NOTES SPÉCIFIQUES");
      graphStatus.textContent = "Réseau des notes masqué";
    }
    syncGraphToggle();
    draw();
  }

  function renderLegend() {
    // La légende reprend les thèmes : un clic ouvre directement le cercle du thème.
    const legend = $("#legend");
    legend.replaceChildren();
    for (const theme of themeList()) {
      const active = themeFilter === theme.label;
      const text = theme.count ? `${theme.label} · ${theme.count}` : theme.label;
      const button = appendElement(legend, "button", `legend-chip${active ? " active" : ""}`, text);
      button.type = "button";
      button.setAttribute("aria-pressed", String(active));
      const dot = document.createElement("i");
      dot.style.color = colorForGroup(theme.label);
      dot.style.background = colorForGroup(theme.label);
      button.prepend(dot);
      button.addEventListener("click", () => {
        if (!theme.count) return;
        if (themeFilter === theme.label) backToMain();
        else openTheme(theme.label);
        renderLegend();
      });
    }
  }

  function updateGraph(nextGraph, options = {}) {
    if (!nextGraph || !Array.isArray(nextGraph.nodes) || !Array.isArray(nextGraph.links)) return;
    const oldIds = new Set(graph.nodes.map((node) => node.id));
    graph = nextGraph;
    for (const node of graph.nodes) {
      if (!oldIds.has(node.id) && node.id === options.nodeIndex) pulseTimes.set(node.id, performance.now());
    }
    nodesEl.textContent = String(graph.nodes.length);
    linksEl.textContent = String(graph.links.length);
    $("#emptyState").hidden = graph.nodes.length > 0;
    if (!graph.nodes.length) {
      $("#graphSubheading").textContent = "Ajoutez vos notes Markdown pour commencer à explorer vos idées.";
      graphStatus.textContent = "Aucune note indexée";
    }
    renderLegend();
    draw();
    if (Number.isInteger(options.focusIndex)) {
      focusSources(options.focusIds || [options.focusIndex]);
    }
  }

  function addMessage(role, text, options = {}) {
    const message = appendElement(messagesEl, "div", `message ${role}`);
    const avatar = appendElement(message, "div", "message-avatar", role === "user" ? "VOUS" : "J");
    avatar.setAttribute("aria-hidden", "true");
    const body = appendElement(message, "div", "message-body");
    appendElement(body, "div", "message-name", role === "user" ? "VOUS" : "JARVIS");
    appendElement(body, "div", "message-text", text);

    const sourceIds = Array.isArray(options.nodes) ? options.nodes : [];
    if (sourceIds.length) {
      const meta = appendElement(body, "div", "message-meta");
      for (const id of sourceIds.slice(0, 6)) {
        const node = graph.nodes.find((item) => item.id === id);
        if (!node) continue;
        const source = appendElement(meta, "button", "message-source", `✳ ${node.label}`);
        source.type = "button";
        source.title = `Afficher la note « ${node.label} »`;
        source.addEventListener("click", () => selectNode(id));
      }
    }
    if (options.warning) appendElement(body, "div", "message-warning", options.warning);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    if (role === "assistant" && voiceEnabled) speak(text);
    return message;
  }

  function setBusy(value) {
    busy = value;
    sendButton.disabled = value;
    micButton.disabled = value;
    questionInput.disabled = value;
    thinkingLine.hidden = !value;
    $("#thinkingText").textContent = value ? "JARVIS consulte vos notes…" : "JARVIS réfléchit…";
  }

  function isRememberRequest(text) {
    return /^(?:souviens[- ]toi\s+que|rappelle[- ]toi\s+que|note\s+que|remember\s+that|remember\s*:)/i.test(text.trim());
  }

  function isWeatherQuestion(text) {
    const query = normalize(text);
    const asksAboutNotes = /\bnotes?\b/.test(query) && /\b(?:dans|sur|parmi|concerne|enregistre|documente)\b/.test(query);
    const mentionsWeather = /\b(?:meteo|pluie|precipitations?|humidite|temperature|vent|orage|neige)\b/.test(query)
      || /\btemps\b/.test(query) && /\b(?:fait|fera|sanguinet|aujourd|demain|prevision|dehors)\b/.test(query);
    return mentionsWeather && !asksAboutNotes;
  }

  function weatherIcon(code, isDay = true) {
    if (code === 0) return isDay ? "☼" : "☾";
    if (code === 1 || code === 2) return isDay ? "◐" : "☾";
    if (code === 3 || code === 45 || code === 48) return "☁";
    if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return "☂";
    if ([71, 73, 75, 77, 85, 86].includes(code)) return "❄";
    if ([95, 96, 99].includes(code)) return "ϟ";
    return "◌";
  }

  function weatherObservationLabel(value) {
    const match = String(value || "").match(/T(\d{2}:\d{2})/);
    return match ? match[1] : "";
  }

  function windDirectionLabel(degrees) {
    const directions = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
    return directions[Math.round(Number(degrees || 0) / 45) % directions.length];
  }

  function renderWeather(data) {
    const current = data.current;
    if (!current || !Array.isArray(data.daily) || !data.daily.length) return false;
    lastWeatherData = { ...data };
    const stale = data.status === "stale";
    const live = data.status === "live";
    const badge = $("#weatherBadge");
    badge.textContent = live ? "EN DIRECT" : stale ? "EN CACHE" : "DÉMO";
    badge.classList.toggle("live", live);
    badge.classList.toggle("offline", !live);
    // Un champ manquant ne doit jamais afficher « NaN » dans le widget.
    const numeric = (value) => {
      if (value === null || value === undefined || value === "") return null;
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    };
    const temperature = numeric(current.temperature);
    const windSpeed = numeric(current.windSpeed);
    const humidity = numeric(current.humidity);
    const precipitation = numeric(current.precipitation);
    $("#weatherTemp").textContent = temperature === null ? "--" : Math.round(temperature);
    $("#weatherDescription").textContent = current.description || "Conditions actuelles";
    $("#weatherIcon").textContent = weatherIcon(Number(current.code), current.isDay !== false);
    $("#weatherWind").textContent = windSpeed === null
      ? "--"
      : `${Math.round(windSpeed)} km/h ${windDirectionLabel(current.windDirection)}`;
    $("#weatherHumidity").textContent = humidity === null ? "--" : `${Math.round(humidity)}%`;
    $("#weatherPrecip").textContent = precipitation === null
      ? "--"
      : `${precipitation.toFixed(precipitation % 1 ? 1 : 0)} mm`;

    const observation = weatherObservationLabel(data.updatedAt);
    $("#weatherUpdated").textContent = stale
      ? `Dernière mesure ${observation ? `à ${observation}` : "en cache"}`
      : `Open-Meteo · actualisé ${observation ? `à ${observation}` : "maintenant"}`;
    $("#forecastDays").setAttribute("aria-label", stale ? "Dernières prévisions Open-Meteo conservées sur cinq jours" : "Prévisions Open-Meteo sur cinq jours");
    const forecastItems = document.querySelectorAll("[data-forecast-day]");
    const dateFormatter = new Intl.DateTimeFormat("fr-FR", { weekday: "short", timeZone: "Europe/Paris" });
    forecastItems.forEach((item, index) => {
      const forecast = data.daily[index];
      const date = forecast ? new Date(`${forecast.date}T12:00:00Z`) : null;
      if (!date || Number.isNaN(date.getTime())) {
        item.querySelector("[data-forecast-label]").textContent = "--";
        item.querySelector("[data-forecast-icon]").textContent = "◌";
        item.querySelector("[data-forecast-range]").textContent = "--";
        item.setAttribute("aria-label", "Prévision indisponible");
        return;
      }
      const label = dateFormatter.format(date).replace(/\.$/, "").toLocaleUpperCase("fr-FR");
      const high = numeric(forecast.max);
      const low = numeric(forecast.min);
      const range = high !== null && low !== null ? `${Math.round(high)}° / ${Math.round(low)}°` : "--";
      item.querySelector("[data-forecast-label]").textContent = index === 0 ? "AUJ." : label;
      item.querySelector("[data-forecast-icon]").textContent = weatherIcon(Number(forecast.code));
      item.querySelector("[data-forecast-range]").textContent = range;
      item.setAttribute("aria-label", `${label} : ${range} degrés, ${weatherIcon(Number(forecast.code))}`);
    });

    const fishingNote = windSpeed !== null && windSpeed >= 30
      ? `Vent soutenu (${Math.round(windSpeed)} km/h) · prudence au bord de l’eau.`
      : (precipitation !== null && precipitation > 0) || [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99].includes(Number(current.code))
        ? "Précipitations possibles ou en cours · prévoyez une protection."
        : windSpeed === null
          ? "Vent non communiqué · indication météo seulement."
          : `Vent ${windDirectionLabel(current.windDirection)} ${Math.round(windSpeed)} km/h · indication météo seulement.`;
    $("#weatherFishingNote").textContent = fishingNote;

    const agentState = $("#weatherAgentState");
    agentState.textContent = live ? "EN DIRECT" : "EN CACHE";
    agentState.classList.toggle("live", live);
    agentState.classList.toggle("offline", !live);
    const agentDot = $("#weatherAgentDot");
    agentDot.classList.remove("status-cyan", "status-live", "status-slate");
    agentDot.classList.add(live ? "status-live" : "status-slate");
    $("#agentLiveNote").textContent = live
      ? "OPEN-METEO EN DIRECT · 7 AUTRES PROFILS EN DÉMO"
      : "DERNIÈRE MESURE EN CACHE · 7 AUTRES PROFILS EN DÉMO";
    return true;
  }

  function showWeatherUnavailable() {
    const badge = $("#weatherBadge");
    badge.textContent = "DÉMO";
    badge.classList.remove("live");
    badge.classList.add("offline");
    $("#weatherUpdated").textContent = "Open-Meteo indisponible · valeurs d’exemple";
    $("#forecastDays").setAttribute("aria-label", "Prévisions météo de démonstration sur cinq jours");
    $("#weatherFishingNote").textContent = "Météo en direct indisponible · données d’exemple";
    $("#weatherAgentState").textContent = "HORS LIGNE";
    $("#weatherAgentState").classList.remove("live");
    $("#weatherAgentState").classList.add("offline");
    const agentDot = $("#weatherAgentDot");
    agentDot.classList.remove("status-cyan", "status-live");
    agentDot.classList.add("status-slate");
    $("#agentLiveNote").textContent = "MÉTÉO INDISPONIBLE · 7 AUTRES PROFILS EN DÉMO";
  }

  function markWeatherStale(message) {
    if (!lastWeatherData) {
      showWeatherUnavailable();
      return null;
    }
    const data = {
      ...lastWeatherData,
      status: "stale",
      warning: message || "Le serveur météo est momentanément injoignable; voici la dernière mesure reçue.",
    };
    renderWeather(data);
    return data;
  }

  async function loadWeather() {
    try {
      const response = await fetch("/api/weather", { headers: { Accept: "application/json" } });
      const data = await response.json();
      if (!response.ok || !renderWeather(data)) markWeatherStale(data.error);
    } catch (_error) {
      markWeatherStale();
    }
  }

  function weatherAnswer(data) {
    const current = data.current;
    const sourceNote = data.status === "stale" ? " (dernière mesure en cache)" : "";
    const observation = weatherObservationLabel(data.updatedAt);
    const measure = (value) => {
      if (value === null || value === undefined || value === "") return null;
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    };
    const temperature = measure(current.temperature);
    const feels = measure(current.apparentTemperature) ?? temperature;
    const wind = measure(current.windSpeed);
    const humidity = measure(current.humidity);
    const rain = measure(current.precipitation);
    const describe = (value, suffix) => (value === null ? "non communiqué" : `${Math.round(value)}${suffix}`);
    return `À Sanguinet${observation ? `, mesure de ${observation}` : ""} : ${describe(temperature, " °C")}, ressenti ${describe(feels, " °C")}, ${String(current.description || "conditions inconnues").toLocaleLowerCase("fr-FR")}. Vent ${describe(wind, " km/h")}, humidité ${describe(humidity, " %")}, précipitations ${rain === null ? "non communiquées" : `${rain.toFixed(1)} mm`}${sourceNote}. Source : Open-Meteo.`;
  }

  async function sendQuestion(rawText) {
    const text = String(rawText || "").trim();
    if (!text || busy) return;
    addMessage("user", text);
    questionInput.value = "";
    questionInput.style.height = "auto";
    setBusy(true);
    const remembering = isRememberRequest(text);
    const askingWeather = !remembering && isWeatherQuestion(text);
    $("#thinkingText").textContent = remembering
      ? "JARVIS enregistre ce souvenir…"
      : askingWeather ? "JARVIS consulte Open-Meteo…" : "JARVIS consulte vos notes…";
    try {
      if (askingWeather) {
        const response = await fetch("/api/weather", { headers: { Accept: "application/json" } });
        const data = await response.json();
        if (!response.ok || !renderWeather(data)) {
          const stale = markWeatherStale(data.error);
          if (stale) {
            addMessage("assistant", weatherAnswer(stale), { warning: stale.warning });
            graphStatus.textContent = "Dernière mesure météo conservée · cache";
          } else {
            addMessage("assistant", "Je ne parviens pas à joindre Open-Meteo pour le moment, monsieur. Les valeurs du widget sont des exemples, pas la météo actuelle.", { warning: data.error });
            graphStatus.textContent = "Météo en direct indisponible · exemples affichés";
          }
        } else {
          addMessage("assistant", weatherAnswer(data), { warning: data.warning });
          graphStatus.textContent = data.status === "stale" ? "Dernière mesure Open-Meteo · cache" : "Météo Open-Meteo · Sanguinet";
        }
        return;
      }
      const response = await fetch(remembering ? "/api/remember" : "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: remembering ? text : undefined, question: remembering ? undefined : text }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "La demande n’a pas abouti.");
      if (remembering) {
        if (data.graph) updateGraph(data.graph, { nodeIndex: data.nodeIndex, parentIndex: data.parentIndex, focusIndex: data.nodeIndex });
        addMessage("assistant", data.answer || `C’est noté, monsieur. « ${data.title} » a rejoint votre galaxie.`, { nodes: Number.isInteger(data.nodeIndex) ? [data.nodeIndex] : [] });
        graphStatus.textContent = "Souvenir ajouté à la galaxie";
      } else {
        const nodes = Array.isArray(data.nodes) ? data.nodes : [];
        addMessage("assistant", data.answer || "Je n’ai pas de réponse à vous proposer.", { nodes, warning: data.warning });
        if (nodes.length) focusSources(nodes);
        if (data.localMode) graphStatus.textContent = "Recherche locale dans vos notes";
      }
    } catch (error) {
      if (askingWeather) {
        const stale = markWeatherStale();
        if (stale) {
          addMessage("assistant", weatherAnswer(stale), { warning: stale.warning });
          graphStatus.textContent = "Dernière mesure météo conservée · cache";
        } else {
          addMessage("assistant", "La météo en direct n’est pas joignable, monsieur. Les valeurs conservées dans le widget sont des exemples.");
          graphStatus.textContent = "Météo en direct indisponible · exemples affichés";
        }
      } else {
        addMessage("assistant", error.message || "La connexion locale a été interrompue. Vérifiez que le serveur JARVIS tourne encore.");
        graphStatus.textContent = "Connexion à la passerelle interrompue";
      }
    } finally {
      setBusy(false);
      questionInput.focus();
    }
  }

  async function loadStatus() {
    try {
      const response = await fetch("/api/status", { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const status = await response.json();
      const aiReady = Boolean(status.aiConfigured);
      $("#connectionLabel").textContent = aiReady ? "IA CONNECTÉE" : "INDEX LOCAL PRÊT";
      $("#brainLabel").textContent = aiReady ? "ANTHROPIC ACTIF" : "MODE LOCAL";
      $("#modelLabel").textContent = aiReady ? String(status.model || "MODÈLE IA").toLocaleUpperCase("fr-FR") : "RECHERCHE SUR VOS NOTES";
      $("#privacyHint").textContent = aiReady ? "Extraits pertinents envoyés à Anthropic" : "Vos notes restent sur cet appareil";
      $("#buildLabel").textContent = aiReady ? "IA PRIVÉE PAR LE SERVEUR" : "LOCAL FIRST";
      if (status.isDemo) {
        graphStatus.textContent = "Exemples fictifs — remplacez-les par vos notes";
        $("#graphSubheading").textContent = `${graph.nodes.length} notes de démonstration indexées. Vous pourrez les remplacer par vos propres fichiers Markdown.`;
      } else if (graph.nodes.length) {
        graphStatus.textContent = "Index local prêt · notes privées";
        $("#graphSubheading").textContent = `${graph.nodes.length} notes indexées. Explorez les liens entre vos idées.`;
      }
      if (status.noteCount !== graph.nodes.length) {
        const graphResponse = await fetch("/api/graph", { headers: { Accept: "application/json" } });
        if (graphResponse.ok) updateGraph(await graphResponse.json());
      }
    } catch (_error) {
      $("#connectionLabel").textContent = "PASSERELLE HORS LIGNE";
      graphStatus.textContent = "Démarrez le serveur avec python3 server.py";
    }
  }

  // --- Voix et animation de JARVIS -------------------------------------------------
  // La synthèse vocale pilote trois calques (portrait, yeux, lumière de la bouche).
  // Sans événement de frontière (navigateur qui ne les émet pas), le rythme reste
  // assuré par les animations CSS ; sinon la lumière de la bouche suit les syllabes.
  const SPEECH_FALLBACK_DELAY = 320;
  const SPEECH_WATCHDOG_INTERVAL = 900;

  function setJarvisSpeaking(isSpeaking) {
    stage.classList.toggle("jarvis-speaking", isSpeaking);
    document.body.classList.toggle("jarvis-speaking", isSpeaking);
    const label = $("#stageModeLabel");
    if (label) label.textContent = isSpeaking ? "JARVIS PARLE" : "RÉSEAU LOCAL";
    if (!isSpeaking) {
      if (core) core.style.setProperty("--jarvis-voice", "0");
      boundaryCount = 0;
      window.clearTimeout(boundaryTimer);
      boundaryTimer = null;
    }
  }

  function speechText(text) {
    // La synthèse ne doit pas lire la syntaxe Markdown, les URL ni le code.
    return String(text || "")
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/`([^`]*)`/g, "$1")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/https?:\/\/\S+/g, " ")
      .replace(/\*\*|__|~~|[*_#>|]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function pickFrenchVoice(voices) {
    if (!Array.isArray(voices) || !voices.length) return null;
    return voices.find((voice) => /^fr[-_]fr/i.test(voice.lang || ""))
      || voices.find((voice) => /^fr/i.test(voice.lang || ""))
      || null;
  }

  function withVoices(callback) {
    // Chrome charge la liste des voix après le premier clic : on attend un court instant
    // pour éviter de lire le français avec une voix anglaise.
    const synth = window.speechSynthesis;
    let voices = [];
    try { voices = synth.getVoices() || []; } catch (_error) { voices = []; }
    if (voices.length) return callback(voices);
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      synth.removeEventListener?.("voiceschanged", finish);
      let updated = [];
      try { updated = synth.getVoices() || []; } catch (_error) { updated = []; }
      callback(updated);
    };
    synth.addEventListener?.("voiceschanged", finish);
    window.setTimeout(finish, 420);
  }

  function pulseVoiceGlow() {
    if (!core) return;
    boundaryCount += 1;
    // Chaque syllabe relance l'éclat du disque et de l'orbe ; le retour au calme est
    // légèrement aléatoire pour éviter un métronome visible.
    const energy = .55 + Math.random() * .45;
    window.clearTimeout(boundaryTimer);
    core.style.setProperty("--jarvis-voice", energy.toFixed(2));
    boundaryTimer = window.setTimeout(() => {
      if (core) core.style.setProperty("--jarvis-voice", ".12");
    }, 95 + Math.random() * 85);
  }

  function stopSpeechVisuals(token) {
    if (token !== undefined && token !== speechToken) return;
    window.clearInterval(speechWatchdog);
    speechWatchdog = null;
    window.clearTimeout(speechFallback);
    speechFallback = null;
    setJarvisSpeaking(false);
  }

  function speak(text) {
    if (!voiceEnabled || !("speechSynthesis" in window)) return;
    const sentence = speechText(text);
    if (!sentence) return;
    const synth = window.speechSynthesis;
    const token = ++speechToken;
    stopSpeechVisuals();
    try { synth.cancel(); } catch (_error) { /* navigateur sans annulation : sans effet */ }
    withVoices((voices) => {
      if (token !== speechToken || !voiceEnabled) return;
      const utterance = new SpeechSynthesisUtterance(sentence);
      utterance.lang = "fr-FR";
      utterance.rate = .97;
      utterance.pitch = .94;
      utterance.voice = pickFrenchVoice(voices);
      utterance.onstart = () => {
        if (token === speechToken && voiceEnabled) setJarvisSpeaking(true);
      };
      utterance.onboundary = (event) => {
        if (token !== speechToken || !voiceEnabled) return;
        if (event && event.name && event.name !== "word") return;
        pulseVoiceGlow();
      };
      utterance.onend = () => stopSpeechVisuals(token);
      utterance.onerror = () => stopSpeechVisuals(token);
      try {
        synth.speak(utterance);
      } catch (_error) {
        stopSpeechVisuals(token);
        return;
      }
      // Certains navigateurs n'émettent jamais « start » : on affiche quand même la
      // parole, mais seulement si la synthèse est réellement active.
      window.clearTimeout(speechFallback);
      speechFallback = window.setTimeout(() => {
        if (token !== speechToken || !voiceEnabled) return;
        if (synth.speaking || synth.pending) setJarvisSpeaking(true);
      }, SPEECH_FALLBACK_DELAY);
      // Filet de sécurité : plus aucune activité alors que l'animation tourne.
      window.clearInterval(speechWatchdog);
      speechWatchdog = window.setInterval(() => {
        if (token !== speechToken) {
          window.clearInterval(speechWatchdog);
          speechWatchdog = null;
          return;
        }
        if (synth.speaking || synth.pending) return;
        stopSpeechVisuals(token);
      }, SPEECH_WATCHDOG_INTERVAL);
    });
  }

  function toggleVoice() {
    if (!("speechSynthesis" in window)) {
      graphStatus.textContent = "La synthèse vocale n’est pas disponible dans ce navigateur";
      return;
    }
    voiceEnabled = !voiceEnabled;
    const button = $("#voiceToggle");
    button.setAttribute("aria-pressed", String(voiceEnabled));
    $("#voiceToggleLabel").textContent = voiceEnabled ? "VOIX ACTIVE" : "VOIX OFF";
    if (voiceEnabled) {
      const count = graph.nodes.length;
      const lastAssistant = [...messagesEl.querySelectorAll(".message.assistant .message-text")].pop();
      const greeting = count
        ? `Bonjour, monsieur. ${count} notes indexées, toutes présentes et bien rangées.`
        : "Bonjour, monsieur. Je suis prêt à indexer vos premières notes.";
      // Relire la dernière réponse est plus utile qu'un bonjour répété à chaque activation.
      speak(voiceBooted && lastAssistant ? lastAssistant.textContent : greeting);
      voiceBooted = true;
    } else {
      speechToken += 1;
      try { window.speechSynthesis.cancel(); } catch (_error) { /* sans effet */ }
      stopSpeechVisuals();
    }
  }

  function startDictation() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      graphStatus.textContent = "Dictée indisponible — utilisez Chrome ou Edge";
      addMessage("assistant", "La dictée vocale demande Chrome ou Edge, monsieur. Le clavier, lui, est toujours à vos ordres.");
      return;
    }
    if (recognition) {
      recognition.stop();
      return;
    }
    recognition = new SpeechRecognition();
    recognition.lang = "fr-FR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      micButton.classList.add("listening");
      micButton.setAttribute("aria-label", "Arrêter la dictée");
      graphStatus.textContent = "Écoute en cours… parlez maintenant";
    };
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || "";
      questionInput.value = transcript;
      if (transcript) sendQuestion(transcript);
    };
    recognition.onerror = (event) => {
      const message = event.error === "not-allowed" ? "Autorisez le micro dans votre navigateur pour dicter." : "La dictée n’a pas pu démarrer. Réessayez.";
      graphStatus.textContent = message;
    };
    recognition.onend = () => {
      micButton.classList.remove("listening");
      micButton.setAttribute("aria-label", "Dicter un message");
      recognition = null;
      if (!busy) graphStatus.textContent = "Index local prêt";
    };
    try {
      recognition.start();
    } catch (_error) {
      recognition = null;
      graphStatus.textContent = "Impossible d’ouvrir le micro. Réessayez dans un instant.";
    }
  }

  function onPointerDown(event) {
    if (event.button !== undefined && event.button !== 0) return;
    const point = pointFromEvent(event);
    pointerStart = { ...point, startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, moved: false };
    dragging = true;
    targetRotation = null;
    canvas.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event) {
    const point = pointFromEvent(event);
    if (pointerStart && dragging) {
      const dx = event.clientX - pointerStart.lastX;
      const dy = event.clientY - pointerStart.lastY;
      if (Math.hypot(event.clientX - pointerStart.startX, event.clientY - pointerStart.startY) > 4) pointerStart.moved = true;
      rotationY += dx * .006;
      rotationX = Math.max(-1.35, Math.min(1.35, rotationX + dy * .005));
      pointerStart.lastX = event.clientX;
      pointerStart.lastY = event.clientY;
      if (pointerStart.moved) {
        draw();
        return;
      }
    }
    const node = pickNode(point.x, point.y);
    hoveredId = node ? node.id : null;
    canvas.style.cursor = node ? "pointer" : dragging ? "grabbing" : "grab";
  }

  function onPointerUp(event) {
    if (!pointerStart) return;
    const point = pointFromEvent(event);
    const wasClick = !pointerStart.moved;
    pointerStart = null;
    dragging = false;
    if (wasClick) {
      const node = pickNode(point.x, point.y);
      if (node) selectNode(node.id);
    }
  }

  function zoomBy(amount) {
    targetRotation = null;
    targetZoom = Math.max(.68, Math.min(1.8, targetZoom + amount));
    zoom = targetZoom;
    draw();
  }

  function resetView() {
    rotationX = .11;
    rotationY = 0;
    zoom = 1;
    targetZoom = 1;
    targetRotation = null;
    selectedId = null;
    clusterIds = [];
    focusedIds.clear();
    labelIds.clear();
    textIds.clear();
    graphOverview = false;
    searchTerm = "";
    $("#searchInput").value = "";
    activeGroup = null;
    level = "themes";
    themeFilter = null;
    focusId = null;
    syncGraphToggle();
    $("#sectorLabel").textContent = "TOUS LES THÈMES";
    sourceContent.hidden = true;
    sourceEmpty.hidden = false;
    renderLegend();
    updateStageHint("VOS NOTES, CLASSÉES PAR THÈME · CLIQUEZ SUR UN POINT POUR OUVRIR SES NOTES");
    draw();
  }

  function updateClock() {
    const now = new Date();
    const date = $("#currentDate");
    if (date) date.textContent = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" }).format(now);
    const clock = $("#topClock");
    if (clock) clock.textContent = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(now);
  }

  function openHelp() {
    if (!helpDialog) return;
    if (typeof helpDialog.showModal === "function" && !helpDialog.open) helpDialog.showModal();
    else helpDialog.setAttribute("open", "");
  }

  function closeHelp() {
    if (!helpDialog || !helpDialog.open) return;
    if (typeof helpDialog.close === "function") helpDialog.close();
    else helpDialog.removeAttribute("open");
  }

  function wireEvents() {
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    canvas.addEventListener("pointerleave", () => { if (!dragging) hoveredId = null; });
    canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      zoomBy(event.deltaY < 0 ? .08 : -.08);
    }, { passive: false });
    $("#zoomIn").addEventListener("click", () => zoomBy(.12));
    $("#zoomOut").addEventListener("click", () => zoomBy(-.12));
    $("#resetView").addEventListener("click", resetView);
    $("#toggleGraph").addEventListener("click", toggleGraphOverview);
    $("#voiceToggle").addEventListener("click", toggleVoice);
    micButton.addEventListener("click", startDictation);
    $("#chatForm").addEventListener("submit", (event) => {
      event.preventDefault();
      sendQuestion(questionInput.value);
    });
    questionInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendQuestion(questionInput.value);
      }
    });
    questionInput.addEventListener("input", () => {
      questionInput.style.height = "auto";
      questionInput.style.height = `${Math.min(questionInput.scrollHeight, 100)}px`;
    });
    $("#searchInput").addEventListener("input", (event) => {
      searchTerm = normalize(event.target.value.trim());
      const matches = graph.nodes.filter((node) => normalize(`${node.label} ${node.excerpt}`).includes(searchTerm));
      if (searchTerm) {
        graphOverview = false;
        selectedId = null;
        focusedIds.clear();
        clusterIds = [];
        labelIds = new Set(matches.slice(0, 6).map((node) => node.id));
        textIds = new Set(Array.from(labelIds).slice(0, 4));
        graphStatus.textContent = `${matches.length} résultat${matches.length === 1 ? "" : "s"} dans les notes`;
        if (matches.length === 1) {
          selectedId = matches[0].id;
          focusedIds = new Set([matches[0].id, ...neighborsOf(matches[0].id)]);
          renderSourcePanel(matches[0]);
        }
      } else {
        labelIds = selectedId === null ? new Set() : new Set([selectedId]);
        textIds = selectedId === null ? new Set() : new Set([selectedId]);
        if (selectedId === null) focusedIds.clear();
        graphStatus.textContent = "Index local prêt";
      }
      syncGraphToggle();
      draw();
    });
    const hintBack = $("#hintBack");
    if (hintBack) {
      hintBack.addEventListener("click", () => {
        if (level === "detail") { if (themeFilter) openTheme(themeFilter); else backToMain(); }
        else backToMain();
      });
    }
    $("#helpButton").addEventListener("click", openHelp);
    $("#closeHelp").addEventListener("click", closeHelp);
    helpDialog.addEventListener("click", (event) => {
      if (event.target === helpDialog) closeHelp();
    });
    document.querySelectorAll("[data-prompt]").forEach((button) => {
      button.addEventListener("click", () => sendQuestion(button.dataset.prompt));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
        event.preventDefault();
        $("#searchInput").focus();
      }
      if (event.key === "Escape") {
        // Échap remonte d'un cercle : note → thème → thèmes.
        if (helpDialog && helpDialog.open) closeHelp();
        else if (level === "detail") { if (themeFilter) openTheme(themeFilter); else backToMain(); }
        else if (level === "main" && !searchTerm) backToMain();
      }
    });
  }

  function greet() {
    const count = graph.nodes.length;
    const greeting = count
      ? `Bonjour, monsieur. ${count} notes indexées, toutes présentes et bien rangées. Comment puis-je vous aider ?`
      : "Bonjour, monsieur. Je suis prêt à indexer vos premières notes Markdown. Une mémoire vide, c’est très calme — presque suspect.";
    addMessage("assistant", greeting);
  }

  if (graph.nodes.some((node, index) => node.id !== index)) {
    // L'index numérique des nœuds est un contrat utilisé par le serveur et l'interface.
    graph.nodes.forEach((node, index) => { node.id = index; });
  }
  // Le cœur holographique apparaît d'un bloc, une fois toutes ses couches prêtes :
  // sinon on voyait les anneaux se poser un par un au rythme du chargement.
  function revealCore() {
    const images = Array.from(document.querySelectorAll(".jarvis-core img"));
    const done = () => document.body.classList.add("core-ready");
    const ready = images.map((image) => {
      if (!image.decode) return Promise.resolve();
      return image.decode().catch(() => {
        // Repli : si le navigateur ne décode pas l'AVIF, on repasse au PNG.
        const source = image.src || "";
        if (!source.endsWith(".avif")) return undefined;
        image.src = source.replace(/\.avif(\?.*)?$/, ".png");
        return image.decode ? image.decode().catch(() => undefined) : undefined;
      });
    });
    Promise.all(ready).then(done).catch(done);
    window.setTimeout(done, 2500); // filet de sécurité : jamais de scène vide
  }

  updateGraph(graph);
  createStars();
  revealCore();
  wireEvents();
  resizeCanvas();
  updateClock();
  window.setInterval(updateClock, 60_000);
  greet();
  loadStatus();
  loadWeather();
  window.setInterval(loadWeather, 10 * 60 * 1000);
  if ("ResizeObserver" in window) new ResizeObserver(resizeCanvas).observe(stage);
  else window.addEventListener("resize", resizeCanvas);
  window.requestAnimationFrame(frame);
})();
