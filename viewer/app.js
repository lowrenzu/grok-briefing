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
  const hologram = $(".jarvis-hologram");
  const voiceLayer = $(".jarvis-hologram-voice");

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
  const positions = new Map();
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
  }

  function makePosition(index, total) {
    const y = 1 - (2 * (index + .5)) / Math.max(total, 1);
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const angle = Math.PI * (3 - Math.sqrt(5)) * index;
    return { x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius };
  }

  function ensurePositions(parentIndex = null) {
    const count = graph.nodes.length;
    for (let index = 0; index < count; index += 1) {
      const node = graph.nodes[index];
      if (positions.has(node.id)) continue;
      let parent = Number.isInteger(parentIndex) ? parentIndex : null;
      if (parent === node.id || !positions.has(parent)) parent = null;
      if (parent === null) {
        const link = graph.links.find((item) => {
          const source = typeof item.source === "object" ? item.source.id : item.source;
          const target = typeof item.target === "object" ? item.target.id : item.target;
          return source === node.id && positions.has(target) || target === node.id && positions.has(source);
        });
        if (link) {
          const source = typeof link.source === "object" ? link.source.id : link.source;
          const target = typeof link.target === "object" ? link.target.id : link.target;
          parent = source === node.id ? target : source;
        }
      }
      if (parent !== null && positions.has(parent)) {
        const origin = positions.get(parent);
        const angle = index * 2.399963229728653;
        const offset = .18 + (index % 3) * .035;
        const candidate = {
          x: origin.x + Math.cos(angle) * offset,
          y: origin.y + Math.sin(angle * .8) * offset,
          z: origin.z + Math.sin(angle) * offset,
        };
        const length = Math.hypot(candidate.x, candidate.y, candidate.z) || 1;
        positions.set(node.id, { x: candidate.x / length, y: candidate.y / length, z: candidate.z / length });
      } else {
        positions.set(node.id, makePosition(index, count));
      }
    }
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

  function projectPoint(position) {
    const cosY = Math.cos(rotationY);
    const sinY = Math.sin(rotationY);
    const x1 = position.x * cosY + position.z * sinY;
    const z1 = -position.x * sinY + position.z * cosY;
    const cosX = Math.cos(rotationX);
    const sinX = Math.sin(rotationX);
    const y2 = position.y * cosX - z1 * sinX;
    const z2 = position.y * sinX + z1 * cosX;
    const factor = 1 / (1.62 - z2 * .43);
    const base = Math.min(width, height);
    const viewScale = Math.min(1.08, Math.max(1, zoom));
    const worldRadius = base * .48 * viewScale * factor;
    let offsetX = x1 * worldRadius;
    let offsetY = y2 * worldRadius;
    const distance = Math.hypot(offsetX, offsetY);
    // Maintient les notes en orbite autour de l’hologramme central, sans recouvrir le visage.
    const orbitRadius = base * .42 * viewScale;
    if (distance < orbitRadius) {
      const angle = distance > .001 ? Math.atan2(offsetY, offsetX) : Math.atan2(position.y, position.x) + rotationY;
      offsetX = Math.cos(angle) * orbitRadius;
      offsetY = Math.sin(angle) * orbitRadius;
    }
    return {
      x: width / 2 + offsetX,
      y: height / 2 + offsetY,
      z: z2,
      factor,
      radius: worldRadius,
    };
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

    for (const star of stars) {
      const twinkle = .65 + .35 * Math.sin(time * .8 + star.phase);
      const starX = star.x * width;
      const starY = star.y * height;
      const fromCenter = Math.hypot(starX - width / 2, starY - height / 2);
      const avatarClear = Math.min(width, height) * .31;
      const fade = Math.max(.08, Math.min(1, (fromCenter - avatarClear) / (Math.min(width, height) * .13)));
      context.globalAlpha = star.alpha * twinkle * fade;
      context.fillStyle = "#d9f5fb";
      context.beginPath();
      context.arc(starX, starY, star.size, 0, Math.PI * 2);
      context.fill();
    }
    context.globalAlpha = 1;

    const centerGlow = context.createRadialGradient(width / 2, height / 2, 4, width / 2, height / 2, Math.min(width, height) * .43);
    centerGlow.addColorStop(0, "rgba(55, 143, 160, .045)");
    centerGlow.addColorStop(.5, "rgba(31, 73, 91, .02)");
    centerGlow.addColorStop(1, "rgba(9, 17, 27, 0)");
    context.fillStyle = centerGlow;
    context.fillRect(0, 0, width, height);

    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    const projected = new Map(graph.nodes.map((node) => [node.id, projectPoint(positions.get(node.id) || { x: 0, y: 0, z: 0 })]));
    const activeIds = new Set(focusedIds);
    if (selectedId !== null) {
      activeIds.add(selectedId);
      for (const id of neighborsOf(selectedId)) activeIds.add(id);
    }
    if (clusterIds.length) clusterIds.forEach((id) => activeIds.add(id));
    const showGraph = graphOverview || selectedId !== null || focusedIds.size > 0 || labelIds.size > 0 || activeGroup !== null;
    stage.classList.toggle("showing-graph", showGraph);
    if (!showGraph) {
      projectedNodes = [];
      return;
    }

    let drawnFocusEdges = 0;
    const focusEdgeLimit = labelIds.size >= 4 ? 18 : 12;
    for (const link of graph.links) {
      const { source, target } = linkIds(link);
      const relevantEdge = labelIds.has(source) || labelIds.has(target) || source === hoveredId || target === hoveredId;
      if (!graphOverview && activeGroup === null && !relevantEdge) continue;
      if (!graphOverview && activeGroup === null && drawnFocusEdges >= focusEdgeLimit) continue;
      if (!graphOverview && activeGroup === null) drawnFocusEdges += 1;
      const a = projected.get(source);
      const b = projected.get(target);
      if (!a || !b) continue;
      const bright = labelIds.has(source) && labelIds.has(target) || labelIds.size <= 1 && (source === selectedId || target === selectedId);
      const inGroup = activeGroup === null || byId.get(source)?.group === activeGroup && byId.get(target)?.group === activeGroup;
      const inSearch = !searchTerm || normalize(byId.get(source)?.label + " " + byId.get(source)?.excerpt).includes(searchTerm) || normalize(byId.get(target)?.label + " " + byId.get(target)?.excerpt).includes(searchTerm);
      if (activeGroup !== null && !inGroup) continue;
      const centerX = width / 2;
      const centerY = height / 2;
      const startAngle = Math.atan2(a.y - centerY, a.x - centerX);
      const endAngle = Math.atan2(b.y - centerY, b.x - centerX);
      let angleDelta = endAngle - startAngle;
      while (angleDelta > Math.PI) angleDelta -= Math.PI * 2;
      while (angleDelta < -Math.PI) angleDelta += Math.PI * 2;
      const arcRadius = (Math.hypot(a.x - centerX, a.y - centerY) + Math.hypot(b.x - centerX, b.y - centerY)) / 2;
      context.beginPath();
      context.arc(centerX, centerY, arcRadius, startAngle, startAngle + angleDelta, angleDelta < 0);
      context.lineWidth = bright ? 1.25 : .55;
      context.strokeStyle = bright ? "rgba(113, 232, 228, .66)" : "rgba(107, 196, 217, .14)";
      const opacity = graphOverview ? (bright ? .22 : .045) : bright ? .4 : .12;
      context.globalAlpha = (inGroup && inSearch ? 1 : .2) * opacity * (.45 + ((a.z + b.z + 2) / 4) * .55);
      context.stroke();
    }
    context.globalAlpha = 1;

    const ordered = graph.nodes.filter((node) => {
      const matchSearch = !searchTerm || normalize(`${node.label} ${node.excerpt}`).includes(searchTerm);
      const matchGroup = activeGroup === null || node.group === activeGroup;
      return matchGroup && (graphOverview || activeIds.has(node.id) || node.id === hoveredId || Boolean(searchTerm) && matchSearch || activeGroup !== null);
    }).map((node) => ({ node, point: projected.get(node.id) })).sort((a, b) => a.point.z - b.point.z);
    projectedNodes = ordered;
    for (const { node, point } of ordered) {
      const isSelected = selectedId === node.id;
      const isHovered = hoveredId === node.id;
      const isFocused = activeIds.has(node.id);
      const isSourceNode = labelIds.has(node.id);
      const matchSearch = !searchTerm || normalize(`${node.label} ${node.excerpt}`).includes(searchTerm);
      const matchGroup = activeGroup === null || node.group === activeGroup;
      const dimmed = !matchSearch || !matchGroup;
      const base = Math.max(2.4, Math.min(5.8, 3 + (node.connections || 0) * .28));
      const radius = base * (.72 + point.factor * .38) * (isSelected ? 1.55 : isHovered ? 1.35 : 1);
      const color = colorForGroup(node.group || "notes");
      const pulseStart = pulseTimes.get(node.id);
      const age = pulseStart ? (performance.now() - pulseStart) / 1000 : 9;
      if (age < 2.2) {
        const pulse = age / 2.2;
        context.beginPath();
        context.arc(point.x, point.y, radius + pulse * 22, 0, Math.PI * 2);
        context.strokeStyle = color;
        context.globalAlpha = (1 - pulse) * .7;
        context.lineWidth = 1.4;
        context.stroke();
        context.globalAlpha = 1;
      }

      context.save();
      const nodeOpacity = isSelected || isHovered ? .96 : isSourceNode ? .88 : isFocused ? .16 : graphOverview ? .11 : searchTerm && matchSearch ? .7 : activeGroup !== null ? .28 : .12;
      context.globalAlpha = dimmed ? .045 : nodeOpacity;
      context.shadowColor = color;
      context.shadowBlur = isFocused || isSelected || isHovered ? 20 : 10;
      context.beginPath();
      context.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context.fillStyle = color;
      context.fill();
      context.shadowBlur = 0;
      context.beginPath();
      context.arc(point.x, point.y, radius + (isFocused ? 4 : 2.3), 0, Math.PI * 2);
      context.strokeStyle = color;
      context.globalAlpha = dimmed ? .025 : isSelected || isHovered || isSourceNode ? .76 : isFocused ? .13 : graphOverview ? .07 : activeGroup !== null ? .22 : .08;
      context.lineWidth = isSelected || isSourceNode ? 1.1 : .65;
      context.stroke();
      context.restore();

      const shouldLabel = isSelected || isHovered || textIds.has(node.id);
      if (shouldLabel && !dimmed) {
        context.save();
        const radialX = point.x - width / 2;
        const radialY = point.y - height / 2;
        const radialLength = Math.hypot(radialX, radialY) || 1;
        const outwardX = radialX / radialLength;
        const outwardY = radialY / radialLength;
        context.globalAlpha = isSelected || isHovered ? .98 : .88;
        context.font = `${isSelected ? 9 : 8}px ui-monospace, SFMono-Regular, Menlo, monospace`;
        context.textAlign = outwardX > .25 ? "left" : outwardX < -.25 ? "right" : "center";
        context.textBaseline = "middle";
        context.shadowColor = "rgba(0, 0, 0, .98)";
        context.shadowBlur = 6;
        context.fillStyle = isSelected ? "#f3ffff" : "#d0edf3";
        const label = node.label.length > 22 ? `${node.label.slice(0, 20)}…` : node.label;
        const labelX = point.x + outwardX * (radius + 6);
        const labelY = point.y + outwardY * (radius + 6);
        context.fillText(label, labelX, labelY, 126);
        context.restore();
      }
    }
    context.globalAlpha = 1;
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

  function cameraTo(id, extraZoom = 1.22) {
    const point = positions.get(id);
    if (!point) return;
    const yAngle = Math.atan2(-point.x, point.z);
    const zAfterYaw = Math.hypot(point.x, point.z);
    const xAngle = Math.atan2(point.y, zAfterYaw || .001);
    targetRotation = { x: xAngle, y: yAngle, zoom: extraZoom };
  }

  function cameraToCluster(ids) {
    const points = ids.map((id) => positions.get(id)).filter(Boolean);
    if (!points.length) return;
    const center = points.reduce((sum, point) => ({ x: sum.x + point.x, y: sum.y + point.y, z: sum.z + point.z }), { x: 0, y: 0, z: 0 });
    center.x /= points.length; center.y /= points.length; center.z /= points.length;
    const length = Math.hypot(center.x, center.y, center.z) || 1;
    cameraToPoint({ x: center.x / length, y: center.y / length, z: center.z / length }, points.length > 7 ? 1.04 : 1.12);
  }

  function cameraToPoint(point, nextZoom) {
    targetRotation = {
      y: Math.atan2(-point.x, point.z),
      x: Math.atan2(point.y, Math.hypot(point.x, point.z) || .001),
      zoom: nextZoom,
    };
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

  function selectNode(id, options = {}) {
    const node = graph.nodes.find((item) => item.id === id);
    if (!node) return;
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

  function updateStageHint(text) {
    $("#stageHint").textContent = text;
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
      updateStageHint("JARVIS AU CENTRE · CHOISISSEZ UN UNIVERS OU POSEZ UNE QUESTION");
      graphStatus.textContent = "Réseau des notes masqué";
    }
    syncGraphToggle();
    draw();
  }

  function renderLegend() {
    const legend = $("#legend");
    legend.replaceChildren();
    const groups = Array.from(new Set(graph.nodes.map((node) => node.group || "Mes notes"))).sort((a, b) => a.localeCompare(b, "fr"));
    for (const group of groups) {
      const button = appendElement(legend, "button", `legend-chip${activeGroup === group ? " active" : ""}`, group);
      button.type = "button";
      button.setAttribute("aria-pressed", String(activeGroup === group));
      const dot = document.createElement("i");
      dot.style.color = colorForGroup(group);
      dot.style.background = colorForGroup(group);
      button.prepend(dot);
      button.addEventListener("click", () => {
        activeGroup = activeGroup === group ? null : group;
        $("#sectorLabel").textContent = activeGroup ? activeGroup.toLocaleUpperCase("fr-FR") : "TOUTES LES NOTES";
        renderLegend();
        draw();
      });
    }
  }

  function updateGraph(nextGraph, options = {}) {
    if (!nextGraph || !Array.isArray(nextGraph.nodes) || !Array.isArray(nextGraph.links)) return;
    const oldIds = new Set(graph.nodes.map((node) => node.id));
    graph = nextGraph;
    ensurePositions(options.parentIndex);
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
      hologram?.classList.remove("voice-synced");
      if (voiceLayer) voiceLayer.style.removeProperty("opacity");
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
    if (!voiceLayer) return;
    boundaryCount += 1;
    if (boundaryCount === 2 && hologram) hologram.classList.add("voice-synced");
    const energy = .28 + Math.random() * .52;
    window.clearTimeout(boundaryTimer);
    voiceLayer.style.opacity = energy.toFixed(2);
    boundaryTimer = window.setTimeout(() => {
      if (voiceLayer) voiceLayer.style.opacity = ".14";
    }, 96 + Math.random() * 90);
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
    syncGraphToggle();
    $("#sectorLabel").textContent = "TOUTES LES NOTES";
    document.querySelectorAll(".category-node").forEach((node) => node.classList.remove("active"));
    sourceContent.hidden = true;
    sourceEmpty.hidden = false;
    renderLegend();
    updateStageHint("JARVIS AU CENTRE · CHOISISSEZ UN UNIVERS OU POSEZ UNE QUESTION");
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
    document.querySelectorAll(".category-node").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".category-node").forEach((node) => node.classList.remove("active"));
        button.classList.add("active");
        $("#sectorLabel").textContent = button.dataset.category || "TOUTES LES NOTES";
        updateStageHint(`UNIVERS ${button.dataset.category || "SÉLECTIONNÉ"} · JARVIS CONSULTE VOTRE MÉMOIRE`);
      });
    });
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
      if (event.key === "Escape") closeHelp();
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
  ensurePositions();
  updateGraph(graph);
  createStars();
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
