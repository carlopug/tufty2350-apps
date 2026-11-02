
(() => {
  for (const C of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!C) continue;
    const orig = C.prototype.texSubImage2D;
    C.prototype.texSubImage2D = function(...a) {
      const src = a[a.length - 1];
      if (src instanceof Uint8Array && a.length >= 9) {
        const w = a[4], h = a[5];
        if ((w == 160 && h == 120) || (w == 320 && h == 240))
          window.__fb = {w, h, data: src.slice()};
      }
      return orig.apply(this, a);
    };
  }
  window.__fbPng = (scala) => {
    const f = window.__fb; if (!f) return null;
    const n = f.data.length / (f.w * f.h);
    const c = document.createElement('canvas'); c.width = f.w; c.height = f.h;
    const ctx = c.getContext('2d'); const img = ctx.createImageData(f.w, f.h);
    for (let i = 0; i < f.w * f.h; i++) {
      img.data[4*i] = f.data[n*i]; img.data[4*i+1] = f.data[n*i+1];
      img.data[4*i+2] = f.data[n*i+2]; img.data[4*i+3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    const k = scala * 320 / f.w;
    const g = document.createElement('canvas'); g.width = f.w * k; g.height = f.h * k;
    const gx = g.getContext('2d'); gx.imageSmoothingEnabled = false;
    gx.drawImage(c, 0, 0, g.width, g.height);
    return g.toDataURL('image/png');
  };
})();
