/* Swap map: a dotted map of India where signals arc between the cities of members who are swapping.
 * Loaded on demand by effects.js. Draws on one <canvas>, only animates while the map is visible,
 * and draws a single still frame (every route traced) for people who prefer reduced motion.
 */
(function () {
  "use strict";

  // Simplified outline of India as [longitude, latitude] pairs. Accurate enough for a dot map.
  var OUTLINE = [
    [74.0, 34.8], [76.0, 35.8], [78.0, 35.3], [79.0, 34.0], [78.8, 32.5], [80.5, 30.5], [83.5, 28.5],
    [88.0, 27.8], [88.2, 26.5], [89.8, 26.4], [92.0, 27.8], [95.5, 28.2], [97.0, 27.5], [95.0, 26.0],
    [94.5, 24.0], [93.3, 23.0], [92.5, 22.0], [92.0, 23.5], [91.5, 24.5], [90.0, 25.2], [89.0, 25.5],
    [88.7, 24.0], [88.9, 22.0], [87.0, 21.5], [86.5, 20.0], [84.8, 19.0], [82.2, 16.6], [80.3, 15.5],
    [80.1, 13.3], [79.8, 11.0], [79.3, 10.3], [78.2, 8.9], [77.5, 8.1], [76.6, 8.9], [76.2, 10.0],
    [75.0, 12.5], [74.5, 14.8], [73.4, 16.5], [72.8, 19.0], [72.9, 20.8], [72.6, 21.3], [72.3, 22.0],
    [70.8, 20.7], [69.0, 22.3], [70.0, 22.8], [68.4, 23.6], [69.5, 24.3], [71.0, 24.4], [70.0, 26.0],
    [70.5, 27.8], [72.2, 28.4], [73.5, 29.9], [74.5, 31.0], [74.0, 32.5], [75.0, 32.8], [74.0, 34.8]
  ];
  var BOUNDS = { minLng: 67.6, maxLng: 97.6, minLat: 7.2, maxLat: 36.4 };
  var X_SQUASH = Math.cos((22 * Math.PI) / 180); // keep India's proportions on a flat map

  function insideOutline(lng, lat) {
    var inside = false;
    for (var i = 0, j = OUTLINE.length - 1; i < OUTLINE.length; j = i++) {
      var xi = OUTLINE[i][0], yi = OUTLINE[i][1], xj = OUTLINE[j][0], yj = OUTLINE[j][1];
      if ((yi > lat) !== (yj > lat) && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function init(root) {
    var source = document.getElementById(root.dataset.source);
    var canvas = root.querySelector("canvas");
    if (!source || !canvas || root.dataset.ready) return;
    root.dataset.ready = "1";

    var data = JSON.parse(source.textContent);
    var ctx = canvas.getContext("2d");
    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var listItems = root.querySelectorAll("[data-city]");

    var W = 0, H = 0, scale = 1, offsetX = 0, offsetY = 0, step = 8;
    var dots = [], points = [], byId = {};
    var signals = [], ripples = [], traces = [];
    var colors = {};
    var hoverId = null, running = false, visible = false, lastLaunch = 0;

    var routes = data.routes.length ? data.routes : [];
    var RATE_MS = 1100;

    function readColors() {
      colors = {
        dot: cssVar("--line") || "#3d3d3d",
        accent: cssVar("--accent") || "#ff6a3d",
        fg: cssVar("--fg") || "#f2f2f2",
        bg: cssVar("--bg") || "#0b0b0b",
        muted: cssVar("--muted") || "#8a8a8a",
        font: cssVar("--mono") || "monospace"
      };
    }

    function project(lng, lat) {
      return [offsetX + (lng - BOUNDS.minLng) * X_SQUASH * scale, offsetY + (BOUNDS.maxLat - lat) * scale];
    }

    function layout() {
      var box = canvas.getBoundingClientRect();
      if (!box.width) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = box.width; H = box.height;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      var geoW = (BOUNDS.maxLng - BOUNDS.minLng) * X_SQUASH;
      var geoH = BOUNDS.maxLat - BOUNDS.minLat;
      scale = Math.min(W / geoW, H / geoH);
      offsetX = (W - geoW * scale) / 2;
      offsetY = (H - geoH * scale) / 2;
      step = Math.max(6, Math.round(W / 64));

      dots = [];
      for (var y = offsetY + step / 2; y < offsetY + geoH * scale; y += step) {
        for (var x = offsetX + step / 2; x < offsetX + geoW * scale; x += step) {
          var lng = BOUNDS.minLng + (x - offsetX) / (X_SQUASH * scale);
          var lat = BOUNDS.maxLat - (y - offsetY) / scale;
          if (insideOutline(lng, lat)) dots.push({ x: x, y: y, glow: 0 });
        }
      }
      points = data.points.map(function (p) {
        var xy = project(p.lng, p.lat);
        var point = { id: p.id, label: p.label, members: p.members, swaps: p.swaps, x: xy[0], y: xy[1] };
        byId[p.id] = point;
        return point;
      });
    }

    function curve(a, b) {
      var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      var dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
      var nx = -dy / len, ny = dx / len;
      if (ny > 0) { nx = -nx; ny = -ny; } // always bow upwards
      var lift = len * 0.3;
      return { ax: a.x, ay: a.y, cx: mx + nx * lift, cy: my + ny * lift, bx: b.x, by: b.y, len: len };
    }

    function at(c, t) {
      var u = 1 - t;
      return [u * u * c.ax + 2 * u * t * c.cx + t * t * c.bx, u * u * c.ay + 2 * u * t * c.cy + t * t * c.by];
    }

    function launch(fromId, toId, now) {
      var a = byId[fromId], b = byId[toId];
      if (!a || !b) return;
      var c = curve(a, b);
      signals.push({ c: c, to: b, start: now, duration: 900 + c.len * 5 });
      traces.push({ c: c, start: now, until: now + 900 + c.len * 5 + 900 });
    }

    function launchRandom(now) {
      if (!routes.length) return;
      var r = routes[Math.floor(Math.random() * routes.length)];
      if (Math.random() < 0.5) launch(r[0], r[1], now); else launch(r[1], r[0], now);
    }

    function strokeCurve(c, alpha, width, color) {
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(c.ax, c.ay);
      ctx.quadraticCurveTo(c.cx, c.cy, c.bx, c.by);
      ctx.stroke();
    }

    function draw(now) {
      ctx.clearRect(0, 0, W, H);
      var size = Math.max(2, step * 0.42);

      // Ripples light up a ring of land dots around the city a signal reached.
      for (var r = ripples.length - 1; r >= 0; r--) {
        var rip = ripples[r], p = (now - rip.start) / 700;
        if (p >= 1) { ripples.splice(r, 1); continue; }
        var radius = p * step * 5;
        for (var d = 0; d < dots.length; d++) {
          var dist = Math.hypot(dots[d].x - rip.x, dots[d].y - rip.y);
          if (Math.abs(dist - radius) < step * 0.75) dots[d].glow = Math.max(dots[d].glow, 1 - p);
        }
      }

      for (var i = 0; i < dots.length; i++) {
        var dot = dots[i];
        ctx.globalAlpha = 1;
        ctx.fillStyle = colors.dot;
        ctx.fillRect(dot.x - size / 2, dot.y - size / 2, size, size);
        if (dot.glow > 0.02) {
          ctx.globalAlpha = dot.glow;
          ctx.fillStyle = colors.accent;
          ctx.fillRect(dot.x - size / 2, dot.y - size / 2, size, size);
          dot.glow *= 0.93;
        } else {
          dot.glow = 0;
        }
      }

      // Faint traces along routes; still mode shows every route.
      if (reduceMotion) {
        routes.forEach(function (route) {
          if (byId[route[0]] && byId[route[1]]) strokeCurve(curve(byId[route[0]], byId[route[1]]), 0.55, 1.5, colors.accent);
        });
      }
      for (var t = traces.length - 1; t >= 0; t--) {
        var tr = traces[t];
        if (now > tr.until) { traces.splice(t, 1); continue; }
        var fade = Math.min(1, (tr.until - now) / 900);
        strokeCurve(tr.c, 0.22 * fade, 1, colors.accent);
      }

      // Signals: a bright head with a fading tail.
      for (var s = signals.length - 1; s >= 0; s--) {
        var sig = signals[s], progress = (now - sig.start) / sig.duration;
        if (progress >= 1) {
          ripples.push({ x: sig.to.x, y: sig.to.y, start: now });
          signals.splice(s, 1);
          continue;
        }
        var eased = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
        var tail = 0.32, segments = 14, prev = at(sig.c, Math.max(0, eased - tail));
        ctx.strokeStyle = colors.accent;
        ctx.lineWidth = 2;
        for (var k = 1; k <= segments; k++) {
          var tt = Math.max(0, eased - tail + (tail * k) / segments);
          var pt = at(sig.c, tt);
          ctx.globalAlpha = k / segments;
          ctx.beginPath();
          ctx.moveTo(prev[0], prev[1]);
          ctx.lineTo(pt[0], pt[1]);
          ctx.stroke();
          prev = pt;
        }
        ctx.globalAlpha = 1;
        ctx.fillStyle = colors.fg;
        ctx.fillRect(prev[0] - 2.5, prev[1] - 2.5, 5, 5);
      }

      // City markers.
      points.forEach(function (point) {
        var active = point.id === hoverId;
        var m = active ? 10 : 7;
        ctx.globalAlpha = 1;
        ctx.fillStyle = colors.bg;
        ctx.fillRect(point.x - m / 2 - 2, point.y - m / 2 - 2, m + 4, m + 4);
        ctx.fillStyle = colors.accent;
        ctx.fillRect(point.x - m / 2, point.y - m / 2, m, m);
      });

      // Label for the hovered city.
      var hovered = hoverId && byId[hoverId];
      if (hovered) {
        var text = hovered.label.toUpperCase() + "  " + hovered.members + " MEMBER" + (hovered.members === 1 ? "" : "S");
        ctx.font = "500 11px " + colors.font;
        var tw = ctx.measureText(text).width, bx = hovered.x + 12, by = hovered.y - 26;
        if (bx + tw + 16 > W) bx = hovered.x - tw - 28;
        ctx.globalAlpha = 1;
        ctx.fillStyle = colors.fg;
        ctx.fillRect(bx, by, tw + 16, 22);
        ctx.fillStyle = colors.bg;
        ctx.fillText(text, bx + 8, by + 15);
      }
      ctx.globalAlpha = 1;
    }

    function frame(now) {
      if (!running) return;
      if (now - lastLaunch > RATE_MS) { launchRandom(now); lastLaunch = now; }
      draw(now);
      requestAnimationFrame(frame);
    }

    function start() {
      if (running || reduceMotion || !visible || document.hidden) return;
      running = true;
      requestAnimationFrame(frame);
    }
    function stop() { running = false; }

    function setHover(id) {
      if (hoverId === id) return;
      hoverId = id;
      listItems.forEach(function (li) { li.classList.toggle("is-active", li.dataset.city === id); });
      if (!running) draw(performance.now());
    }

    function nearest(event) {
      var box = canvas.getBoundingClientRect(), x = event.clientX - box.left, y = event.clientY - box.top;
      var best = null, bestDist = 16;
      points.forEach(function (p) {
        var d = Math.hypot(p.x - x, p.y - y);
        if (d < bestDist) { best = p; bestDist = d; }
      });
      return best;
    }

    canvas.addEventListener("pointermove", function (event) {
      var p = nearest(event);
      canvas.style.cursor = p ? "pointer" : "";
      setHover(p ? p.id : null);
    });
    canvas.addEventListener("pointerleave", function () { setHover(null); });
    canvas.addEventListener("click", function (event) {
      var p = nearest(event);
      if (!p) return;
      var now = performance.now();
      routes.forEach(function (r) {
        if (r[0] === p.id) launch(p.id, r[1], now);
        else if (r[1] === p.id) launch(p.id, r[0], now);
      });
      ripples.push({ x: p.x, y: p.y, start: now });
      if (reduceMotion) draw(now);
    });
    listItems.forEach(function (li) {
      li.addEventListener("mouseenter", function () { setHover(li.dataset.city); });
      li.addEventListener("focus", function () { setHover(li.dataset.city); });
      li.addEventListener("mouseleave", function () { setHover(null); });
      li.addEventListener("blur", function () { setHover(null); });
    });

    readColors();
    layout();
    draw(performance.now());

    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
      if (visible) start(); else stop();
    }).observe(canvas);
    document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); else start(); });
    if ("ResizeObserver" in window) {
      new ResizeObserver(function () { layout(); draw(performance.now()); }).observe(canvas);
    }
    // Follow the light/dark toggle.
    new MutationObserver(function () { readColors(); draw(performance.now()); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ["data-bs-theme"] });
  }

  document.querySelectorAll("[data-signal-map]").forEach(init);
})();
