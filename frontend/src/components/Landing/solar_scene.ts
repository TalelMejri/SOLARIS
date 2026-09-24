import * as THREE from "three";
import {
  KWMAX,
  MODES,
  clamp01,
  clearSky,
  elevation,
  hex,
  mix,
  type SimState,
} from "./solar";

export interface SolarSceneOptions {
  /** empty element the scene appends its own <canvas> to (and removes on dispose) */
  mount: HTMLElement;
  /** element whose size the canvas follows (the hero section) */
  container: HTMLElement;
  /** shared mutable state: the scene reads t/mode and writes live/shaded */
  sim: SimState;
  reduceMotion: boolean;
}

export interface SolarScene {
  frame: (dt: number, now: number, moving: boolean) => void;
  dispose: () => void;
}

interface FlowRec {
  curve: THREE.CatmullRomCurve3;
  geo: THREE.BufferGeometry;
  mat: THREE.PointsMaterial;
  u: number[];
}
interface ArrayRec {
  group: THREE.Group;
  meshes: THREE.Mesh[];
  shaded: number;
  f: number;
  samples: THREE.Vector3[];
  flow: FlowRec | null;
}
interface Puff {
  m: THREE.Mesh;
  r: number;
}
interface CloudData {
  puffs: Puff[];
  speed: number;
  s: number;
  base: number;
}
interface Sphere {
  c: THREE.Vector3;
  r: number;
}

function rng(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createSolarScene(opts: SolarSceneOptions): SolarScene | null {
  const { mount, container, sim, reduceMotion } = opts;
  const rand = rng(11);

  // A fresh canvas per mount: React StrictMode mounts twice in dev, and a canvas whose
  // context was lost (forceContextLoss) can never create a new WebGL context.
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  canvas.style.cssText = "display:block;width:100%;height:100%";
  mount.appendChild(canvas);

  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
  } catch {
    canvas.remove();
    return null;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 1, 400);
  const target = new THREE.Vector3(0, 2.2, 0);

  /* ---------- environment for panel reflections ---------- */
  const envTarget = (() => {
    const envScene = new THREE.Scene();
    const eg = new THREE.SphereGeometry(40, 32, 16);
    const pos = eg.attributes.position;
    const col: number[] = [];
    const cTop = new THREE.Color(0x5b9be0);
    const cHor = new THREE.Color(0xf4f9ff);
    const cBot = new THREE.Color(0x9a8c72);
    for (let i = 0; i < pos.count; i++) {
      const y = pos.getY(i) / 40;
      const c = y > 0 ? cHor.clone().lerp(cTop, Math.pow(y, 0.6)) : cHor.clone().lerp(cBot, Math.min(1, -y * 2));
      col.push(c.r, c.g, c.b);
    }
    eg.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    envScene.add(new THREE.Mesh(eg, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide })));
    const glint = new THREE.Mesh(
      new THREE.SphereGeometry(7, 16, 8),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(1.6, 1.55, 1.4) }),
    );
    glint.position.set(-13, 27, -4);
    envScene.add(glint);
    const pm = new THREE.PMREMGenerator(renderer);
    const rt = pm.fromScene(envScene, 0.04);
    pm.dispose();
    eg.dispose();
    return rt;
  })();

  /* ---------- lights (physically based units, hence the PI factor) ---------- */
  const hemi = new THREE.HemisphereLight(0xbcd8ff, 0xd8c9a8, Math.PI * 0.6);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff1dc, Math.PI * 1.1);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const sc = sun.shadow.camera;
  sc.left = -15;
  sc.right = 15;
  sc.top = 15;
  sc.bottom = -15;
  sc.near = 10;
  sc.far = 120;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.03;
  scene.add(sun, sun.target);
  sun.target.position.copy(target);

  /* ---------- materials ---------- */
  const std = (color: number, rough = 0.9, metal = 0) =>
    new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal });
  const wallMat = std(0xf5f7fa);
  const parapetMat = std(0xe6ecf2);
  const blueMat = std(0x1f5fa8, 0.6);
  const glassMat = std(0x9fc4e8, 0.25, 0.1);
  const groundMat = std(0xcabc9d);
  const plinthMat = std(0x8f836b);
  const steelMat = std(0x8593a3, 0.5, 0.5);
  const greenMat = std(0x2f5d46, 0.95);
  const bushMat = std(0x5f8f5a, 0.95);
  const goldMat = std(0xe8b23a, 0.35, 0.6);
  const legMat = std(0x56616e, 0.6, 0.6);

  const box = (w: number, h: number, d: number, mat: THREE.Material) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.castShadow = true;
    m.receiveShadow = true;
    return m;
  };

  /* ---------- solar panel texture + materials ---------- */
  const anis = renderer.capabilities.getMaxAnisotropy();
  const cellTex = (() => {
    const c = document.createElement("canvas");
    c.width = 512;
    c.height = 352;
    const g = c.getContext("2d")!;
    g.fillStyle = "#0d2a52";
    g.fillRect(0, 0, 512, 352);
    const cols = 10;
    const rows = 6;
    const pad = 12;
    const cw = (512 - pad * 2) / cols;
    const ch = (352 - pad * 2) / rows;
    for (let r = 0; r < rows; r++) {
      for (let q = 0; q < cols; q++) {
        const x = pad + q * cw;
        const y = pad + r * ch;
        const gr = g.createLinearGradient(x, y, x + cw, y + ch);
        gr.addColorStop(0, "#1d4f92");
        gr.addColorStop(1, "#123a75");
        g.fillStyle = gr;
        g.fillRect(x + 2, y + 2, cw - 4, ch - 4);
        g.strokeStyle = "rgba(205,220,240,.38)";
        g.lineWidth = 1;
        g.beginPath();
        g.moveTo(x + cw * 0.33, y + 2);
        g.lineTo(x + cw * 0.33, y + ch - 2);
        g.moveTo(x + cw * 0.66, y + 2);
        g.lineTo(x + cw * 0.66, y + ch - 2);
        g.stroke();
      }
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = anis;
    return t;
  })();

  const panelTop = new THREE.MeshStandardMaterial({
    map: cellTex,
    emissiveMap: cellTex,
    emissive: new THREE.Color(0x2d6bff),
    emissiveIntensity: 0.1,
    metalness: 0.55,
    roughness: 0.24,
    envMap: envTarget.texture,
    envMapIntensity: 0.85,
  });
  const frameMat = new THREE.MeshStandardMaterial({
    color: 0xcbd5df,
    metalness: 0.8,
    roughness: 0.35,
    envMap: envTarget.texture,
    envMapIntensity: 0.6,
  });
  const panelMats = [frameMat, frameMat, panelTop, frameMat, frameMat, frameMat];
  const PW = 1.25;
  const PD = 0.85;
  const TILT = THREE.MathUtils.degToRad(28);
  const panelGeo = new THREE.BoxGeometry(PW, 0.05, PD);

  function makeArray(cols: number, rows: number, s: number): ArrayRec {
    const group = new THREE.Group();
    const meshes: THREE.Mesh[] = [];
    const pitchX = PW + 0.07;
    const pitchZ = 1.55;
    const totalW = (cols - 1) * pitchX + PW;
    for (let r = 0; r < rows; r++) {
      const row = new THREE.Group();
      row.position.z = (r - (rows - 1) / 2) * pitchZ;
      group.add(row);
      const tg = new THREE.Group();
      tg.position.y = 0.38;
      tg.rotation.x = TILT;
      row.add(tg);
      for (let c = 0; c < cols; c++) {
        const p = new THREE.Mesh(panelGeo, panelMats);
        p.position.x = (c - (cols - 1) / 2) * pitchX;
        p.castShadow = true;
        p.receiveShadow = true;
        tg.add(p);
        meshes.push(p);
      }
      [-totalW / 2 + 0.15, totalW / 2 - 0.15].forEach((x) => {
        const back = box(0.05, 0.58, 0.05, legMat);
        back.position.set(x, 0.29, -0.375);
        row.add(back);
        const front = box(0.05, 0.18, 0.05, legMat);
        front.position.set(x, 0.09, 0.36);
        row.add(front);
      });
    }
    group.scale.setScalar(s);
    return { group, meshes, shaded: 0, f: 0, samples: [], flow: null };
  }

  /* ---------- diorama base ---------- */
  const plinth = box(16.6, 0.6, 12.6, plinthMat);
  plinth.position.y = -0.9;
  const slab = box(16, 0.6, 12, groundMat);
  slab.position.y = -0.3;
  scene.add(plinth, slab);

  /* ---------- houses ---------- */
  const makeWindow = (wd: number, hg: number) => {
    const g = new THREE.Group();
    g.add(box(wd, hg, 0.09, blueMat));
    g.add(box(wd * 0.62, hg * 0.72, 0.1, glassMat));
    return g;
  };

  interface HouseOpts {
    x: number;
    z: number;
    w: number;
    d: number;
    h: number;
    dome?: boolean;
  }
  const arrays: ArrayRec[] = [];

  function house(o: HouseOpts, cols = 0, rows = 0, s = 1) {
    const g = new THREE.Group();
    g.position.set(o.x, 0, o.z);
    const { w, d, h } = o;
    const body = box(w, h, d, wallMat);
    body.position.y = h / 2;
    g.add(body);

    const t = 0.18;
    const ph = 0.32;
    const parapets: [number, number, number, number, number][] = [
      [w, ph, t, 0, d / 2 - t / 2],
      [w, ph, t, 0, -d / 2 + t / 2],
      [t, ph, d - 2 * t, w / 2 - t / 2, 0],
      [t, ph, d - 2 * t, -w / 2 + t / 2, 0],
    ];
    parapets.forEach((a) => {
      const p = box(a[0], a[1], a[2], parapetMat);
      p.position.set(a[3], h + ph / 2, a[4]);
      g.add(p);
    });

    const nf = Math.max(1, Math.floor((w - 0.8) / 1.5));
    for (let i = 0; i < nf; i++) {
      const x = (i - (nf - 1) / 2) * 1.5;
      const wu = makeWindow(0.55, 0.75);
      wu.position.set(x, h * 0.68, d / 2 + 0.02);
      g.add(wu);
      if (h > 2.5 && x > -w / 2 + 1.9) {
        const wl = makeWindow(0.55, 0.75);
        wl.position.set(x, 1.0, d / 2 + 0.02);
        g.add(wl);
      }
    }
    const dr = box(0.85, 1.4, 0.1, blueMat);
    dr.position.set(-w / 2 + 1.0, 0.7, d / 2 + 0.03);
    g.add(dr);

    const ns = Math.max(1, Math.floor((d - 0.8) / 1.6));
    for (let j = 0; j < ns; j++) {
      const zz = (j - (ns - 1) / 2) * 1.6;
      const ws = makeWindow(0.55, 0.75);
      ws.rotation.y = Math.PI / 2;
      ws.position.set(w / 2 + 0.02, h * 0.62, zz);
      g.add(ws);
    }

    if (o.dome) {
      const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.85, 0.85, 0.45, 28), wallMat);
      drum.position.y = h + 0.225;
      drum.castShadow = true;
      drum.receiveShadow = true;
      g.add(drum);
      const dome = new THREE.Mesh(new THREE.SphereGeometry(0.85, 28, 12, 0, Math.PI * 2, 0, Math.PI / 2), blueMat);
      dome.position.y = h + 0.45;
      dome.castShadow = true;
      dome.receiveShadow = true;
      g.add(dome);
      const fin = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), goldMat);
      fin.position.y = h + 0.45 + 0.9;
      g.add(fin);
    }

    if (cols) {
      const a = makeArray(cols, rows, s);
      a.group.position.y = h;
      g.add(a.group);
      arrays.push(a);
    }
    scene.add(g);
  }

  // arrays[0] is the main roof: it drives the live readout
  house({ x: 0, z: 0, w: 6.0, d: 4.6, h: 3.4 }, 4, 2, 1.0);
  house({ x: -5.4, z: -1.0, w: 3.2, d: 3.0, h: 2.4, dome: true });
  house({ x: 5.2, z: 0.4, w: 3.2, d: 3.4, h: 2.8 }, 2, 1, 0.8);
  house({ x: -4.6, z: 3.6, w: 2.6, d: 2.2, h: 1.7 }, 2, 1, 0.7);
  house({ x: 3.8, z: -3.8, w: 3.0, d: 2.4, h: 2.0 }, 2, 1, 0.8);
  house({ x: -0.6, z: -4.2, w: 2.8, d: 2.0, h: 1.6 }, 2, 1, 0.7);

  // cypress trees + bushes
  const trees: [number, number, number][] = [
    [1.6, 4.3, 1.0],
    [2.5, 4.6, 0.85],
    [7.0, 3.5, 1.1],
    [-7.2, 2.4, 0.9],
    [-2.4, 4.7, 0.8],
    [7.1, -3.6, 0.9],
  ];
  trees.forEach(([x, z, k]) => {
    const cone = new THREE.Mesh(new THREE.ConeGeometry(0.36 * k, 1.9 * k, 8), greenMat);
    cone.position.set(x, 0.95 * k, z);
    cone.castShadow = true;
    cone.receiveShadow = true;
    scene.add(cone);
  });
  const bushes: [number, number][] = [
    [0.0, 3.6],
    [-6.7, 4.4],
    [6.3, 5.0],
  ];
  bushes.forEach(([x, z]) => {
    const b = new THREE.Mesh(new THREE.SphereGeometry(0.5, 12, 8), bushMat);
    b.position.set(x, 0.3, z);
    b.scale.y = 0.75;
    b.castShadow = true;
    b.receiveShadow = true;
    scene.add(b);
  });

  /* ---------- grid pylon ---------- */
  const pylonPos = new THREE.Vector3(-6.9, 0, -4.4);
  {
    const p = new THREE.Group();
    p.position.copy(pylonPos);
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.55, 5.6, 4), steelMat);
    leg.rotation.y = Math.PI / 4;
    leg.position.y = 2.8;
    leg.castShadow = true;
    p.add(leg);
    const a1 = box(2.6, 0.1, 0.1, steelMat);
    a1.position.y = 5.2;
    const a2 = box(1.8, 0.1, 0.1, steelMat);
    a2.position.y = 4.4;
    const top = box(0.16, 0.5, 0.16, steelMat);
    top.position.y = 5.7;
    p.add(a1, a2, top);
    scene.add(p);
  }

  scene.updateMatrixWorld(true);
  arrays.forEach((a) => {
    a.samples = a.meshes.map((m) => m.getWorldPosition(new THREE.Vector3()));
  });

  /* ---------- power flowing to the grid ---------- */
  const dotTex = (() => {
    const c = document.createElement("canvas");
    c.width = 64;
    c.height = 64;
    const g = c.getContext("2d")!;
    const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, "rgba(255,255,255,1)");
    gr.addColorStop(0.35, "rgba(255,214,110,.9)");
    gr.addColorStop(1, "rgba(255,190,60,0)");
    g.fillStyle = gr;
    g.fillRect(0, 0, 64, 64);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  })();

  const NP = 16;
  arrays.forEach((a, idx) => {
    const start = new THREE.Vector3();
    a.samples.forEach((s) => start.add(s));
    start.multiplyScalar(1 / a.samples.length);
    start.y += 1.0;
    const end = new THREE.Vector3(pylonPos.x + (idx - (arrays.length - 1) / 2) * 0.42, 5.25, pylonPos.z);
    const mid = start.clone().lerp(end, 0.5);
    mid.y += 1.7;
    const curve = new THREE.CatmullRomCurve3([start, mid, end]);
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(curve.getPoints(40)),
      new THREE.LineBasicMaterial({ color: 0xdfe9f5, transparent: true, opacity: 0.5 }),
    );
    scene.add(line);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(NP * 3), 3));
    const mat = new THREE.PointsMaterial({
      map: dotTex,
      size: 0.55,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      opacity: 0,
    });
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    scene.add(pts);
    a.flow = { curve, geo, mat, u: Array.from({ length: NP }, (_, i) => i / NP) };
  });

  /* ---------- clouds ---------- */
  const cloudMat = new THREE.MeshLambertMaterial({
    color: 0xffffff,
    flatShading: true,
    emissive: 0x8fb0d8,
    emissiveIntensity: 0.32,
  });
  const puffGeo = new THREE.IcosahedronGeometry(1, 1);
  const clouds: THREE.Group[] = [];
  for (let ci = 0; ci < 10; ci++) {
    const g = new THREE.Group();
    const puffs: Puff[] = [];
    const n = 4 + Math.floor(rand() * 3);
    for (let k = 0; k < n; k++) {
      const m = new THREE.Mesh(puffGeo, cloudMat);
      const r = 0.9 + rand() * 0.9;
      m.scale.set(r * 1.1, r * 0.78, r);
      m.position.set((k - (n - 1) / 2) * 1.35 + (rand() - 0.5) * 0.5, rand() * 0.5, (rand() - 0.5) * 1.2);
      m.castShadow = true;
      g.add(m);
      puffs.push({ m, r });
    }
    g.position.set(((ci * 0.618) % 1) * 44 - 22, 9.5 + rand() * 2, -2 + rand() * 8);
    const data: CloudData = { puffs, speed: 0.28 + rand() * 0.25, s: 0, base: 1 + rand() * 0.5 };
    g.userData = data;
    g.visible = false;
    g.scale.setScalar(0.001);
    scene.add(g);
    clouds.push(g);
  }

  /* ---------- interaction + resize ---------- */
  let px = 0;
  let py = 0;
  let tpx = 0;
  let tpy = 0;
  const AZ0 = 0.5;
  const EL0 = 0.42;
  let baseR = 38;
  let intro = reduceMotion ? 1 : 0;

  const onMove = (e: PointerEvent) => {
    const r = container.getBoundingClientRect();
    tpx = ((e.clientX - r.left) / r.width - 0.5) * 2;
    tpy = ((e.clientY - r.top) / r.height - 0.5) * 2;
  };
  const onLeave = () => {
    tpx = 0;
    tpy = 0;
  };
  container.addEventListener("pointermove", onMove);
  container.addEventListener("pointerleave", onLeave);

  const resize = () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    const desktop = w >= 1024;
    const frac = desktop ? 0.56 : 0.94;
    const visW = 20 / frac;
    const visH = visW / camera.aspect;
    baseR = Math.max(30, visH / 2 / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
    const ox = desktop ? -w * 0.2 : 0;
    const oy = desktop ? h * 0.07 : -h * 0.13;
    camera.setViewOffset(w, h, ox, oy, w, h);
  };
  const ro = new ResizeObserver(resize);
  ro.observe(container);
  resize();

  /* ---------- per-frame ---------- */
  const L = new THREE.Vector3();
  const tmp = new THREE.Vector3();
  const v3 = new THREE.Vector3();
  const spheres: Sphere[] = [];
  const sunWarm = hex(0xffae72);
  const sunWhite = hex(0xfff3e0);

  function shadeAt(p: THREE.Vector3) {
    let best = 0;
    for (const s of spheres) {
      tmp.subVectors(s.c, p);
      const t = tmp.dot(L);
      if (t <= 0) continue;
      const d = Math.sqrt(Math.max(0, tmp.lengthSq() - t * t));
      const v = (s.r - d) / (s.r * 0.45);
      if (v > best) best = v;
    }
    return clamp01(best);
  }

  function update(dt: number, moving: boolean) {
    const t = sim.t;
    const th = Math.PI * t;
    const e = Math.max(0.05, elevation(t));
    L.set(Math.cos(th) * Math.cos(e), Math.sin(e), 0.6 * Math.sin(th) * Math.cos(e)).normalize();
    sun.position.copy(target).addScaledVector(L, 50);
    const k = Math.sqrt(Math.max(0, Math.sin(elevation(t))));
    sun.intensity = Math.PI * (0.15 + 1.1 * k);
    hemi.intensity = Math.PI * (0.34 + 0.32 * k);
    const wc = mix(sunWarm, sunWhite, k);
    sun.color.setRGB(wc[0] / 255, wc[1] / 255, wc[2] / 255, THREE.SRGBColorSpace);

    // clouds
    spheres.length = 0;
    const mm = MODES[sim.mode];
    clouds.forEach((c, i) => {
      const u = c.userData as CloudData;
      const goal = i < mm.n ? 1 : 0;
      u.s += (goal - u.s) * Math.min(1, dt * 1.6);
      if (moving) {
        c.position.x -= u.speed * dt;
        if (c.position.x < -26) {
          c.position.x = 26 + rand() * 4;
          c.position.z = -2 + rand() * 8;
          c.position.y = 9.5 + rand() * 2;
        }
      }
      const s2 = u.base * mm.s * Math.max(0.001, u.s);
      c.scale.setScalar(s2);
      c.visible = u.s > 0.02;
      if (c.visible && u.s > 0.3) {
        for (const pf of u.puffs) {
          spheres.push({
            c: new THREE.Vector3(
              c.position.x + pf.m.position.x * s2,
              c.position.y + pf.m.position.y * s2,
              c.position.z + pf.m.position.z * s2,
            ),
            r: pf.r * s2 * 0.9,
          });
        }
      }
    });

    // shading + power
    const clear = clearSky(t);
    const kk = Math.min(1, dt * 6);
    for (const a of arrays) {
      let sum = 0;
      for (const p of a.samples) sum += shadeAt(p);
      a.shaded += (sum / a.samples.length - a.shaded) * kk;
      a.f = clear * (1 - 0.78 * a.shaded);
    }
    const main = arrays[0];
    sim.shaded = main.shaded;
    sim.live = KWMAX * main.f;
    panelTop.emissiveIntensity = 0.04 + 0.3 * main.f;

    // grid flow
    for (const a of arrays) {
      const fl = a.flow;
      if (!fl) continue;
      fl.mat.opacity = a.f < 0.02 ? 0 : 0.2 + 0.8 * a.f;
      const pos = fl.geo.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < NP; i++) {
        if (moving) fl.u[i] = (fl.u[i] + dt * (0.08 + 0.24 * a.f)) % 1;
        fl.curve.getPoint(fl.u[i], v3);
        pos.setXYZ(i, v3.x, v3.y, v3.z);
      }
      pos.needsUpdate = true;
    }
  }

  function render(dt: number, now: number) {
    if (intro < 1) intro = Math.min(1, intro + dt / 2.6);
    const ik = 1 - Math.pow(1 - intro, 3);
    const introK = 1.22 - 0.22 * ik;
    px += (tpx - px) * Math.min(1, dt * 2.5);
    py += (tpy - py) * Math.min(1, dt * 2.5);
    const sway = reduceMotion ? 0 : Math.sin(now / 7000) * 0.025;
    const az = AZ0 + px * 0.16 + sway - (1 - ik) * 0.25;
    const el = EL0 - py * 0.04 + (1 - ik) * 0.06;
    const r = baseR * introK;
    camera.position.set(
      target.x + r * Math.sin(az) * Math.cos(el),
      target.y + r * Math.sin(el),
      target.z + r * Math.cos(az) * Math.cos(el),
    );
    camera.lookAt(target);
    renderer.render(scene, camera);
  }

  return {
    frame(dt, now, moving) {
      update(dt, moving);
      render(dt, now);
    },
    dispose() {
      ro.disconnect();
      container.removeEventListener("pointermove", onMove);
      container.removeEventListener("pointerleave", onLeave);
      scene.traverse((obj) => {
        const o = obj as THREE.Mesh;
        if (o.geometry) o.geometry.dispose();
        const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
        mats.forEach((m) => m.dispose());
      });
      cellTex.dispose();
      dotTex.dispose();
      envTarget.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    },
  };
}