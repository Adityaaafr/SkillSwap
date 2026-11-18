/* SkillSwap interface effects. Loaded with `defer`, so nothing here delays the first paint.
 *
 *  - Luminous type    [data-luminous]        a drifting spotlight over dimmed text; follows the pointer; click lights it all
 *  - Blur highlight   [data-blur-highlight]  a paragraph that sharpens and marks key phrases when it scrolls into view
 *  - Receipt printer  [data-receipt]         a receipt that feeds out of a printer; drag it up to tear it off
 *  - Signal map       [data-signal-map]      loads js/signal-map.js only when the map is about to scroll into view
 *
 * Every effect respects prefers-reduced-motion and leaves the content readable without JavaScript.
 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var canObserve = "IntersectionObserver" in window;

  function whenVisible(el, callback, rootMargin) {
    if (!canObserve) { callback(); return; }
    var io = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) { io.disconnect(); callback(); return; }
      }
    }, { rootMargin: rootMargin || "0px" });
    io.observe(el);
  }

  /* ---- Luminous type ------------------------------------------------------------------- */
  document.querySelectorAll("[data-luminous]").forEach(function (el) {
    if (reduceMotion) { el.classList.add("is-lit"); return; }
    var queued = false, x = 50, y = 50;

    el.addEventListener("pointermove", function (event) {
      var box = el.getBoundingClientRect();
      x = ((event.clientX - box.left) / box.width) * 100;
      y = ((event.clientY - box.top) / box.height) * 100;
      el.classList.add("is-tracking");
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () {
        queued = false;
        el.style.setProperty("--lx", x.toFixed(1) + "%");
        el.style.setProperty("--ly", y.toFixed(1) + "%");
      });
    });
    el.addEventListener("pointerleave", function () {
      el.classList.remove("is-tracking");
      el.style.removeProperty("--lx");
      el.style.removeProperty("--ly");
    });
    el.addEventListener("click", function () { el.classList.toggle("is-lit"); });

    // Pause the idle drift while the text is off screen.
    if (canObserve) {
      new IntersectionObserver(function (entries) {
        el.classList.toggle("is-paused", !entries[0].isIntersecting);
      }).observe(el);
    }
  });

  /* ---- Blur highlight ------------------------------------------------------------------ */
  document.querySelectorAll("[data-blur-highlight]").forEach(function (el) {
    if (reduceMotion) { el.classList.add("is-in"); return; }
    whenVisible(el, function () { el.classList.add("is-in"); }, "0px 0px -20% 0px");
  });

  /* ---- Receipt printer ----------------------------------------------------------------- */
  document.querySelectorAll("[data-receipt]").forEach(function (root) {
    var paper = root.querySelector(".receipt");
    var button = root.querySelector("[data-receipt-print]");
    var hint = root.querySelector("[data-receipt-hint]");
    var lineCount = root.querySelectorAll(".receipt-paper > *").length;

    function setState(name) {
      root.classList.remove("is-hidden", "is-printing", "is-printed", "is-torn");
      if (name) root.classList.add(name);
    }

    function print() {
      paper.style.transform = "";
      setState("is-hidden");
      void paper.offsetHeight; // apply the hidden position before feeding
      root.style.setProperty("--feed-steps", String(Math.max(lineCount * 2, 12)));
      root.style.setProperty("--feed-ms", Math.min(900 + lineCount * 90, 2600) + "ms");
      setState("is-printing");
      hint.textContent = "Printing…";
    }

    paper.addEventListener("transitionend", function (event) {
      if (event.propertyName !== "transform") return;
      if (root.classList.contains("is-printing")) {
        setState("is-printed");
        hint.textContent = "Drag up to tear off";
      }
    });

    // Tear off: drag the printed receipt upwards (or flick it).
    var startY = null, startTime = 0, dy = 0;
    paper.addEventListener("pointerdown", function (event) {
      if (!root.classList.contains("is-printed")) return;
      startY = event.clientY;
      startTime = performance.now();
      dy = 0;
      paper.setPointerCapture(event.pointerId);
      root.classList.add("is-dragging");
    });
    paper.addEventListener("pointermove", function (event) {
      if (startY === null) return;
      dy = Math.min(0, event.clientY - startY);
      paper.style.transform = "translateY(" + dy + "px) rotate(" + (dy / 45).toFixed(2) + "deg)";
    });
    function release() {
      if (startY === null) return;
      var speed = dy / Math.max(1, performance.now() - startTime);
      startY = null;
      root.classList.remove("is-dragging");
      paper.style.transform = "";
      if (dy < -70 || speed < -0.6) {
        setState("is-torn");
        hint.textContent = "Torn off. Print another?";
      }
    }
    paper.addEventListener("pointerup", release);
    paper.addEventListener("pointercancel", release);

    button.addEventListener("click", print);

    if (reduceMotion || root.dataset.autoplay !== "1") { setState("is-printed"); return; }
    setState("is-hidden");
    whenVisible(root, function () { setTimeout(print, 200); }, "0px 0px -15% 0px");
  });

  /* ---- Signal map: fetch its script only when it is about to be seen ------------------ */
  var map = document.querySelector("[data-signal-map]");
  if (map && map.dataset.src) {
    whenVisible(map, function () {
      var script = document.createElement("script");
      script.src = map.dataset.src;
      script.async = true;
      document.head.appendChild(script);
    }, "400px 0px");
  }
})();
