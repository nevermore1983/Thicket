// The map page. Python sends commands through the bridge (see ui/web/map_bridge.py);
// this file draws them with MapLibre and reports clicks back. It never touches the database.
import * as maplibregl from './vendor/maplibre/maplibre-gl.mjs';

const ONLINE_STYLES = {
  standard: 'https://tiles.openfreemap.org/styles/liberty',
  light: 'https://tiles.openfreemap.org/styles/positron',
  dark: 'https://tiles.openfreemap.org/styles/dark',
};
const SQUARE_ZOOMS = { 10000: [0, 8], 2000: [8, 10], 1000: [10, 24] }; // which size shows when
const HEAT_FADE = [12, 14]; // heat fades out and pins fade in between these zooms
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

let bridge = null;
let map = null;
let reportedOffline = false;
let styleReady = false; // true between 'style.load' and the next setStyle
let queue = Promise.resolve(); // commands run one at a time, in order
const state = {
  theme: null, // colours and pin images from Python
  pins: {}, // category id -> ImageData of its pin
  basemap: 'plain',
  online: false,
  mode: 'pins',
  weight: 'sightings',
  showPlaces: false,
  sightings: null, // URL of the sightings GeoJSON
  squares: {}, // size -> {url, max}
  places: null,
  heat: null, // URL of the heat cells (sightings added up in ~200 m cells, by Python)
  highlight: null, // [lon, lat]
};

const report = (code, message) => bridge && bridge.pageError(code, String(message));
const empty = { type: 'FeatureCollection', features: [] };
const abs = (path) => new URL(path, location.href).href;

function formatDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  const day = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${DAYS[day]} ${d} ${MONTHS[m - 1]} ${y}`;
}

// ---- styles -------------------------------------------------------------------
function plainStyle() {
  const t = state.theme;
  return {
    version: 8,
    sources: { land: { type: 'geojson', data: abs('./uk-outline.geojson'), attribution: 'Outline approximate' } },
    layers: [
      { id: 'water', type: 'background', paint: { 'background-color': t.water } },
      { id: 'land', type: 'fill', source: 'land', paint: { 'fill-color': t.land } },
      { id: 'coast', type: 'line', source: 'land', paint: { 'line-color': t.coast, 'line-width': 1 } },
    ],
  };
}

function styleFor(basemap) {
  return state.online && ONLINE_STYLES[basemap] ? ONLINE_STYLES[basemap] : plainStyle();
}

function useBasemap(basemap) {
  state.basemap = basemap;
  styleReady = false; // our layers are added again on 'style.load'
  map.setStyle(styleFor(basemap), { diff: false });
}

// ---- images (pins and cluster badges) -------------------------------------------
async function decodePins(pins) {
  const out = {};
  for (const [id, b64] of Object.entries(pins)) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0);
    out[id] = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
  }
  return out;
}

function clusterBadge(label) {
  // A round accent badge with the count, drawn at 2x for sharp screens
  const t = state.theme;
  const r = label.length <= 2 ? 15 : label.length === 3 ? 18 : 21;
  const size = (r + 4) * 2 * 2;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.scale(2, 2);
  const c = size / 4;
  ctx.fillStyle = t.accent;
  ctx.globalAlpha = 0.22;
  ctx.beginPath(); ctx.arc(c, c, r + 4, 0, Math.PI * 2); ctx.fill();
  ctx.globalAlpha = 1;
  ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle = t.surface; ctx.stroke();
  ctx.fillStyle = t.accentFg;
  ctx.font = '700 12px "Segoe UI Variable Text", "Segoe UI", sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(label, c, c + 0.5);
  return ctx.getImageData(0, 0, size, size);
}

// MapLibre 6 asks for each image the first time a layer needs it
function resolveImage(id) {
  if (map.hasImage(id)) return;
  if (id.startsWith('n-')) {
    map.addImage(id, clusterBadge(id.slice(2)), { pixelRatio: 2 });
  } else if (id.startsWith('cat-')) {
    const image = state.pins[id.slice(4)] || state.pins.fallback;
    if (image) map.addImage(id, image, { pixelRatio: 2 });
  }
}

// ---- our layers (re-added whenever the background style changes) ------------------
function rampColour(max) {
  // species count / most species in any square, 0..1, onto the ramp's coloured steps
  const ramp = state.theme.ramp;
  const stops = [];
  for (let i = 1; i < ramp.length; i++) stops.push((i - 1) / (ramp.length - 2), ramp[i]);
  return ['interpolate', ['linear'], ['/', ['get', 's'], Math.max(1, max)], ...stops];
}

function addOurLayers() {
  const t = state.theme;
  const data = state.sightings || empty;
  const vis = (on) => (on ? 'visible' : 'none');
  const pins = state.mode === 'pins';
  const heat = state.mode === 'heat';
  const squares = state.mode === 'squares';

  // Only the mode on show gets its sightings: MapLibre keeps several copies of each
  // source's points (one per zoom level), so 20,000 pins loaded twice cost ~100 MB more.
  map.addSource('places', { type: 'geojson', data: state.places || empty });
  if (pins) map.addSource('sightings', { type: 'geojson', data, cluster: true, clusterRadius: 44, clusterMaxZoom: 14 });
  if (heat) map.addSource('sightings-all', { type: 'geojson', data });
  if (heat) map.addSource('heat', { type: 'geojson', data: state.heat || empty });
  map.addSource('highlight', { type: 'geojson', data: highlightData() });
  for (const [size, sq] of Object.entries(state.squares)) map.addSource(`sq-${size}`, { type: 'geojson', data: sq.url });

  map.addLayer({ id: 'places-fill', type: 'fill', source: 'places', layout: { visibility: vis(state.showPlaces) },
    paint: { 'fill-color': t.accent, 'fill-opacity': 0.08 } });
  map.addLayer({ id: 'places-line', type: 'line', source: 'places', layout: { visibility: vis(state.showPlaces) },
    paint: { 'line-color': t.accent, 'line-width': 1.5, 'line-dasharray': [3, 2] } });

  for (const [size, sq] of Object.entries(state.squares)) {
    const [minzoom, maxzoom] = SQUARE_ZOOMS[size];
    map.addLayer({ id: `sq-${size}-fill`, type: 'fill', source: `sq-${size}`, minzoom, maxzoom,
      layout: { visibility: vis(squares) }, paint: { 'fill-color': rampColour(sq.max), 'fill-opacity': 0.72 } });
    map.addLayer({ id: `sq-${size}-line`, type: 'line', source: `sq-${size}`, minzoom, maxzoom,
      layout: { visibility: vis(squares) }, paint: { 'line-color': t.surface, 'line-width': 0.8 } });
  }

  // Each cell's weight is its share of the busiest area (worked out in Python)
  const weight = ['get', state.weight === 'animals' ? 'a' : 's'];
  if (heat) map.addLayer({ id: 'heat', type: 'heatmap', source: 'heat', layout: { visibility: vis(heat) },
    paint: {
      'heatmap-weight': weight,
      // A point adds weight x intensity x 0.4 at its centre, so with the busiest area's
      // weights adding up to 1, intensity 2.5 takes it to the top colour. Zoomed in, a
      // place's sightings spread over more pixels, so intensity rises to compensate.
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 4, 12, 9, 22, 13, 32],
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 4, 2.5, 9, 6, 12, 14],
      'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], HEAT_FADE[0], 0.85, HEAT_FADE[1], 0],
      'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
        0, 'rgba(0,0,0,0)', 0.1, t.ramp[1], 0.3, t.ramp[2], 0.5, t.ramp[3], 0.7, t.ramp[4], 0.85, t.ramp[5], 1, t.ramp[6]],
    } });
  if (heat) map.addLayer({ id: 'heat-pins', type: 'symbol', source: 'sightings-all', minzoom: HEAT_FADE[0],
    layout: { visibility: vis(heat), 'icon-image': ['concat', 'cat-', ['to-string', ['get', 'c']]],
      'icon-allow-overlap': true, 'icon-ignore-placement': true } });

  map.addLayer({ id: 'highlight', type: 'circle', source: 'highlight',
    paint: { 'circle-radius': 17, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': t.accent, 'circle-stroke-width': 3 } });
  if (!pins) return;
  map.addLayer({ id: 'clusters', type: 'symbol', source: 'sightings', filter: ['has', 'point_count'],
    layout: { visibility: vis(pins), 'icon-image': ['concat', 'n-', ['get', 'point_count_abbreviated']],
      'icon-allow-overlap': true, 'icon-ignore-placement': true } });
  map.addLayer({ id: 'pins', type: 'symbol', source: 'sightings', filter: ['!', ['has', 'point_count']],
    layout: { visibility: vis(pins), 'icon-image': ['concat', 'cat-', ['to-string', ['get', 'c']]],
      'icon-allow-overlap': true, 'icon-ignore-placement': true } });
}

function highlightData() {
  if (!state.highlight) return empty;
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: state.highlight } }] };
}

function rebuildOurLayers() {
  // Simplest reliable way to change sources or modes: remove ours and add them again.
  // (While a style is still loading there's nothing to do: 'style.load' adds them.)
  if (!styleReady) return;
  const style = map.getStyle();
  for (const layer of style.layers.filter((l) => OUR_LAYER.test(l.id)).reverse()) map.removeLayer(layer.id);
  for (const id of Object.keys(style.sources).filter((s) => OUR_SOURCE.test(s))) map.removeSource(id);
  addOurLayers();
}
const OUR_LAYER = /^(places-|sq-|heat|highlight$|clusters$|pins$)/;
const OUR_SOURCE = /^(places|sightings|sightings-all|heat|highlight|sq-\d+)$/;

// ---- tooltips and clicks ------------------------------------------------------------
const tip = document.getElementById('tip');
function showTip(point, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  const x = Math.min(point.x + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = point.y + 18 + tip.offsetHeight > window.innerHeight ? point.y - tip.offsetHeight - 10 : point.y + 18;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const plural = (n, word, words) => `${n.toLocaleString('en-GB')} ${n === 1 ? word : words || `${word}s`}`;
const SQUARE_NAMES = { 10000: '10 km square', 2000: '2 km square', 1000: '1 km square' };

function interactiveLayers() {
  if (state.mode === 'pins') return ['pins', 'clusters'];
  if (state.mode === 'heat') return ['heat-pins'];
  return Object.keys(state.squares).map((s) => `sq-${s}-fill`);
}

function onMove(e) {
  const layers = interactiveLayers().filter((id) => map.getLayer(id));
  const features = layers.length ? map.queryRenderedFeatures(e.point, { layers }) : [];
  map.getCanvas().style.cursor = features.length && state.mode !== 'squares' ? 'pointer' : '';
  if (!features.length) { tip.hidden = true; return; }
  const f = features[0];
  const p = f.properties;
  if (p.cluster) {
    showTip(e.point, `<b>${plural(p.point_count, 'sighting')}</b><br><span>Click to zoom in</span>`);
  } else if (p.ref !== undefined) {
    const size = f.layer.id.split('-')[1];
    showTip(e.point, `<b>${esc(p.ref)}</b> <span>(${SQUARE_NAMES[size]})</span><br>${plural(p.s, 'species', 'species')} · ${plural(p.k, 'sighting')}`);
  } else if (features.length > 1) {
    showTip(e.point, `<b>${plural(features.length, 'sighting')} here</b><br><span>Click to list them</span>`);
  } else {
    showTip(e.point, `<b>${esc(p.n)}</b><br><span>${formatDate(p.d)}</span>`);
  }
}

async function onClick(e) {
  const layers = interactiveLayers().filter((id) => map.getLayer(id));
  const features = layers.length ? map.queryRenderedFeatures(e.point, { layers }) : [];
  if (!features.length || state.mode === 'squares') return;
  const f = features[0];
  if (f.properties.cluster) {
    const source = map.getSource('sightings');
    const zoom = await source.getClusterExpansionZoom(f.properties.cluster_id);
    if (zoom <= 15 && zoom > map.getZoom() + 0.01) {
      map.easeTo({ center: f.geometry.coordinates, zoom });
    } else {
      const leaves = await source.getClusterLeaves(f.properties.cluster_id, 1000, 0);
      bridge.clusterPicked(JSON.stringify(leaves.map((l) => l.id)));
    }
  } else if (features.length > 1) {
    bridge.clusterPicked(JSON.stringify(features.map((x) => x.id)));
  } else {
    bridge.sightingClicked(f.id);
  }
}

// ---- errors: fall back to the plain outline when the online map can't load -----------
function onError(e) {
  const message = (e.error && e.error.message) || String(e.error || e);
  const network = /Failed to fetch|AJAXError|NetworkError|ERR_|status 0|blocked/i.test(message);
  if (state.basemap !== 'plain' && network) {
    if (!reportedOffline) {
      reportedOffline = true;
      report('offline', message);
      useBasemap('plain');
    }
    return;
  }
  if (!network) report('script', message);
}

// ---- commands from Python ---------------------------------------------------------------
const commands = {
  async init(a) {
    await commands.setTheme(a, true);
    state.online = a.online;
    state.basemap = a.basemap;
    Object.assign(state, a.layers);
    maplibregl.setWorkerUrl(abs('./vendor/maplibre/maplibre-gl-worker.mjs'));
    map = new maplibregl.Map({
      container: 'map',
      style: styleFor(a.basemap),
      center: [a.camera.lon, a.camera.lat],
      zoom: a.camera.zoom,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      maxPitch: 0,
    });
    window.__map = map; // for tests and debugging in the developer console
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    map.on('style.load', () => { styleReady = true; addOurLayers(); });
    map.setMissingStyleImageResolver(resolveImage);
    map.on('mousemove', onMove);
    map.on('mouseout', () => { tip.hidden = true; });
    map.on('click', onClick);
    map.on('contextmenu', (e) => { tip.hidden = true; bridge.contextMenu(e.lngLat.lat, e.lngLat.lng, map.getZoom()); });
    map.on('moveend', () => {
      const c = map.getCenter();
      bridge.viewChanged(JSON.stringify({ lat: c.lat, lon: c.lng, zoom: map.getZoom() }));
    });
    map.on('error', onError);
    map.once('idle', () => bridge.note('first draw finished'));
  },

  async setTheme({ theme }, first) {
    // Like every command, takes Python's arguments ({theme}); init passes its own, which has one too
    state.theme = theme;
    state.pins = await decodePins(theme.pins);
    const root = document.documentElement.style;
    for (const [k, v] of Object.entries(theme.css)) root.setProperty(`--${k}`, v);
    if (!first && map) {
      for (const id of map.listImages()) if (id.startsWith('n-') || id.startsWith('cat-')) map.removeImage(id);
      if (state.basemap === 'plain') useBasemap('plain'); else rebuildOurLayers();
    }
  },

  setBasemap(a) {
    state.online = a.online;
    reportedOffline = false;
    useBasemap(a.basemap);
  },

  setSightings(a) {
    state.sightings = a.url;
    state.heat = a.heat;
    if (!styleReady) return;
    for (const id of ['sightings', 'sightings-all']) map.getSource(id)?.setData(a.url);
    map.getSource('heat')?.setData(a.heat); // only the sources the current mode has
  },

  setSquares(a) {
    state.squares = a.sizes;
    rebuildOurLayers();
  },

  setPlaces(a) {
    state.places = a.url;
    if (styleReady) map.getSource('places').setData(a.url);
  },

  setLayers(a) {
    Object.assign(state, a);
    tip.hidden = true;
    rebuildOurLayers();
  },

  fit(a) {
    const { west, south, east, north } = a.bounds;
    if (west === east && south === north) map.flyTo({ center: [west, south], zoom: Math.max(map.getZoom(), 13) });
    else map.fitBounds([[west, south], [east, north]], { padding: 48, maxZoom: 14, duration: a.animate ? 700 : 0 });
  },

  flyTo(a) {
    state.highlight = a.highlight ? [a.lon, a.lat] : null;
    if (styleReady) map.getSource('highlight').setData(highlightData());
    map.flyTo({ center: [a.lon, a.lat], zoom: a.zoom, duration: 800 });
  },
};

function run(name, json) {
  queue = queue
    .then(() => commands[name](JSON.parse(json)))
    .catch((err) => report('script', `${name}: ${err && err.stack ? err.stack : err}`));
}

window.addEventListener('error', (e) => report('script', e.message));
new QWebChannel(qt.webChannelTransport, (channel) => {
  bridge = channel.objects.bridge;
  bridge.send.connect(run);
  const gl = document.createElement('canvas').getContext('webgl2');
  if (!gl) {
    bridge.pageError('no_webgl', 'WebGL 2 is not available');
    return;
  }
  bridge.pageReady(JSON.stringify({ webgl: true, maplibre: maplibregl.getVersion() }));
});
