/**
 * roomba-card.js — Custom Lovelace card for the ha-roomba-custom integration
 *
 * Installation:
 *   1. Copy this file to /config/www/roomba-card.js
 *   2. In HA: Settings → Dashboards → Resources → Add Resource
 *      URL: /local/roomba-card.js   Type: JavaScript module
 *   3. Add a Manual card to your dashboard with:
 *      type: custom:roomba-card
 *      entity: vacuum.roomba          # required
 *      name: Roomba                   # optional
 *      battery_entity: sensor.roomba_battery           # optional
 *      bin_entity: binary_sensor.roomba_bin_full       # optional
 *      stuck_entity: binary_sensor.roomba_stuck        # optional
 *      mission_time_entity: sensor.roomba_mission_time # optional
 *      area_entity: sensor.roomba_area_cleaned         # optional
 */

const STYLES = `
  :host { display: block; }
  ha-card {
    padding: 0;
    overflow: hidden;
    font-family: var(--primary-font-family, sans-serif);
  }
  .rc-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 18px 0;
  }
  .rc-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--secondary-text-color);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .rc-conn {
    font-size: 11px;
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--disabled-text-color);
  }
  .rc-conn-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--success-color, #1D9E75);
    transition: background 0.3s;
  }
  .rc-conn-dot.offline { background: var(--error-color, #E24B4A); }
  .rc-body {
    padding: 20px 18px 14px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
  }
  .rc-robot-wrap {
    position: relative;
    width: 120px; height: 120px;
  }
  .rc-ring {
    position: absolute; inset: 0;
    border-radius: 50%;
    box-sizing: border-box;
  }
  .rc-ring-bg {
    border: 3px solid var(--divider-color, rgba(0,0,0,0.12));
  }
  .rc-ring-active {
    border: 3px solid transparent;
    transition: border-color 0.4s;
  }
  .rc-ring-active.cleaning {
    border-top-color: var(--success-color, #1D9E75);
    border-right-color: var(--success-color, #1D9E75);
    animation: rc-spin 1.4s linear infinite;
  }
  .rc-ring-active.returning {
    border-top-color: var(--warning-color, #BA7517);
    border-right-color: var(--warning-color, #BA7517);
    animation: rc-spin 2s linear infinite;
  }
  .rc-ring-active.error {
    border-top-color: var(--error-color, #E24B4A);
    border-right-color: var(--error-color, #E24B4A);
    animation: rc-flash 0.8s ease-in-out infinite;
  }
  .rc-ring-active.docked {
    border-color: var(--info-color, #378ADD);
  }
  .rc-ring-active.paused {
    border-top-color: var(--disabled-text-color, #888780);
    border-right-color: var(--disabled-text-color, #888780);
  }
  @keyframes rc-spin  { to { transform: rotate(360deg); } }
  @keyframes rc-flash { 0%,100% { opacity: 1; } 50% { opacity: 0.25; } }
  .rc-robot-inner {
    position: absolute; inset: 8px;
    border-radius: 50%;
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, rgba(0,0,0,0.12));
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    cursor: default;
  }
  .rc-state-lbl {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    transition: color 0.3s;
  }
  .rc-state-cleaning  { color: var(--success-color, #1D9E75); }
  .rc-state-docked    { color: var(--info-color, #378ADD); }
  .rc-state-returning { color: var(--warning-color, #BA7517); }
  .rc-state-paused    { color: var(--secondary-text-color); }
  .rc-state-error     { color: var(--error-color, #E24B4A); }
  .rc-state-idle      { color: var(--disabled-text-color); }
  .rc-metrics {
    display: flex;
    gap: 20px;
    align-items: center;
  }
  .rc-metric {
    display: flex; flex-direction: column;
    align-items: center; gap: 2px;
  }
  .rc-metric-val {
    font-size: 18px; font-weight: 500;
    color: var(--primary-text-color);
  }
  .rc-metric-lbl {
    font-size: 10px;
    color: var(--disabled-text-color);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .rc-battery-wrap {
    display: flex; align-items: center; gap: 8px;
  }
  .rc-battery-bar {
    width: 60px; height: 6px;
    background: var(--divider-color, rgba(0,0,0,0.12));
    border-radius: 3px; overflow: hidden;
  }
  .rc-battery-fill {
    height: 100%; border-radius: 3px;
    transition: width 0.4s, background 0.4s;
  }
  .rc-battery-pct {
    font-size: 12px; font-weight: 500;
    color: var(--primary-text-color);
    min-width: 32px;
  }
  .rc-divider {
    width: 100%; height: 1px;
    background: var(--divider-color, rgba(0,0,0,0.08));
  }
  .rc-buttons {
    display: flex; gap: 6px;
    width: 100%; justify-content: center;
  }
  .rc-btn {
    flex: 1;
    padding: 9px 4px;
    border: 1px solid var(--divider-color, rgba(0,0,0,0.15));
    border-radius: 8px;
    background: var(--secondary-background-color, #f5f5f5);
    color: var(--primary-text-color);
    cursor: pointer;
    font-size: 10px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-weight: 500;
    display: flex; flex-direction: column;
    align-items: center; gap: 4px;
    transition: background 0.12s, transform 0.1s;
    font-family: inherit;
  }
  .rc-btn:hover   { background: var(--divider-color, rgba(0,0,0,0.1)); }
  .rc-btn:active  { transform: scale(0.95); }
  .rc-btn[disabled] { opacity: 0.4; cursor: not-allowed; }
  .rc-btn.rc-btn-locate { color: var(--info-color, #378ADD); }
  .rc-btn svg { width: 16px; height: 16px; flex-shrink: 0; }
  .rc-pills {
    display: flex; gap: 6px;
  }
  .rc-pill {
    font-size: 10px; padding: 3px 9px;
    border-radius: 20px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-weight: 500;
    border: 1px solid;
    transition: all 0.2s;
  }
  .rc-pill-ok   { background: var(--secondary-background-color); color: var(--disabled-text-color); border-color: var(--divider-color); }
  .rc-pill-warn { background: #FAEEDA; color: #633806; border-color: #EF9F27; }
  .rc-pill-bad  { background: #FCEBEB; color: #791F1F; border-color: #E24B4A; }
  .rc-footer {
    padding: 0 18px 14px;
  }
  .rc-lastcmd {
    font-size: 11px;
    color: var(--disabled-text-color);
  }
  .rc-lastcmd span { color: var(--secondary-text-color); font-weight: 500; }
  .rc-unavail {
    padding: 24px 18px;
    text-align: center;
    color: var(--disabled-text-color);
    font-size: 13px;
  }
`;

const SVG = {
  start:  `<svg viewBox="0 0 16 16"><polygon points="4,2 13,8 4,14" fill="currentColor"/></svg>`,
  pause:  `<svg viewBox="0 0 16 16"><rect x="3" y="2" width="4" height="12" rx="1" fill="currentColor"/><rect x="9" y="2" width="4" height="12" rx="1" fill="currentColor"/></svg>`,
  dock:   `<svg viewBox="0 0 16 16"><path d="M3 13h10M8 3v8M5 7l3 4 3-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`,
  stop:   `<svg viewBox="0 0 16 16"><rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor"/></svg>`,
  locate: `<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M8 1v3M8 12v3M1 8h3M12 8h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
};

const ROBOT_SVG = `<svg width="36" height="36" viewBox="0 0 36 36" fill="none">
  <circle cx="18" cy="18" r="14" fill="none" stroke="var(--divider-color,rgba(0,0,0,0.2))" stroke-width="1.2"/>
  <circle cx="18" cy="18" r="8" fill="var(--divider-color,rgba(0,0,0,0.1))"/>
  <circle cx="18" cy="18" r="3" fill="var(--secondary-text-color,#888)"/>
  <circle cx="18" cy="9"  r="2" fill="var(--secondary-text-color,#888)" opacity="0.6"/>
  <rect x="8"  y="22" width="4" height="2" rx="1" fill="var(--secondary-text-color,#888)" opacity="0.5"/>
  <rect x="24" y="22" width="4" height="2" rx="1" fill="var(--secondary-text-color,#888)" opacity="0.5"/>
</svg>`;

// Map HA vacuum states → display info
function getStateInfo(state) {
  const map = {
    cleaning:  { ring: 'cleaning',  label: 'Cleaning',  cls: 'rc-state-cleaning'  },
    docked:    { ring: 'docked',    label: 'Docked',    cls: 'rc-state-docked'    },
    returning: { ring: 'returning', label: 'Returning', cls: 'rc-state-returning' },
    paused:    { ring: 'paused',    label: 'Paused',    cls: 'rc-state-paused'    },
    idle:      { ring: 'idle',      label: 'Idle',      cls: 'rc-state-idle'      },
    error:     { ring: 'error',     label: 'Stuck!',    cls: 'rc-state-error'     },
    unavailable: { ring: '', label: 'Unavailable', cls: 'rc-state-idle' },
    unknown:     { ring: '', label: 'Unknown',     cls: 'rc-state-idle' },
  };
  return map[state] || { ring: 'idle', label: state, cls: 'rc-state-idle' };
}

class RoombaCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass   = null;
    this._built  = false;
  }

  setConfig(config) {
    if (!config.entity) throw new Error('roomba-card: "entity" is required (e.g. entity: vacuum.roomba)');
    this._config = {
      entity:              config.entity,
      name:                config.name || 'Roomba',
      battery_entity:      config.battery_entity      || null,
      bin_entity:          config.bin_entity           || null,
      stuck_entity:        config.stuck_entity         || null,
      mission_time_entity: config.mission_time_entity  || null,
      area_entity:         config.area_entity          || null,
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._build();
      this._built = true;
    }
    this._update();
  }

  _build() {
    const shadow = this.shadowRoot;
    shadow.innerHTML = `
      <style>${STYLES}</style>
      <ha-card>
        <div class="rc-header">
          <span class="rc-title" id="rc-title">${this._config.name}</span>
          <span class="rc-conn">
            <span class="rc-conn-dot" id="rc-dot"></span>
            <span id="rc-conn-txt">Connecting...</span>
          </span>
        </div>
        <div id="rc-main">
          <div class="rc-body">
            <div class="rc-robot-wrap">
              <div class="rc-ring rc-ring-bg"></div>
              <div class="rc-ring rc-ring-active" id="rc-ring"></div>
              <div class="rc-robot-inner">
                ${ROBOT_SVG}
                <span class="rc-state-lbl" id="rc-state-lbl">—</span>
              </div>
            </div>

            <div class="rc-metrics">
              <div class="rc-metric">
                <span class="rc-metric-val" id="rc-mssn">—</span>
                <span class="rc-metric-lbl">Minutes</span>
              </div>
              <div class="rc-battery-wrap">
                <div class="rc-battery-bar">
                  <div class="rc-battery-fill" id="rc-bat-fill" style="width:0%"></div>
                </div>
                <span class="rc-battery-pct" id="rc-bat-pct">—</span>
              </div>
              <div class="rc-metric">
                <span class="rc-metric-val" id="rc-sqft">—</span>
                <span class="rc-metric-lbl">Sq ft</span>
              </div>
            </div>

            <div class="rc-divider"></div>

            <div class="rc-buttons">
              <button class="rc-btn" id="rc-btn-start"  title="Start cleaning">
                ${SVG.start}Start
              </button>
              <button class="rc-btn" id="rc-btn-pause"  title="Pause">
                ${SVG.pause}Pause
              </button>
              <button class="rc-btn" id="rc-btn-dock"   title="Return to dock">
                ${SVG.dock}Dock
              </button>
              <button class="rc-btn" id="rc-btn-stop"   title="Stop">
                ${SVG.stop}Stop
              </button>
              <button class="rc-btn rc-btn-locate" id="rc-btn-locate" title="Locate (beep)">
                ${SVG.locate}Find
              </button>
            </div>

            <div class="rc-pills">
              <span class="rc-pill rc-pill-ok" id="rc-bin-pill">Bin OK</span>
              <span class="rc-pill rc-pill-ok" id="rc-stuck-pill">Not Stuck</span>
            </div>
          </div>

          <div class="rc-footer">
            <div class="rc-lastcmd">
              Last command: <span id="rc-last-cmd">—</span>
            </div>
          </div>
        </div>
      </ha-card>
    `;

    // Wire up buttons
    const call = (svc, data = {}) => {
      if (!this._hass) return;
      this._hass.callService('vacuum', svc, { entity_id: this._config.entity, ...data });
    };

    shadow.getElementById('rc-btn-start') .addEventListener('click', () => call('start'));
    shadow.getElementById('rc-btn-pause') .addEventListener('click', () => call('pause'));
    shadow.getElementById('rc-btn-dock')  .addEventListener('click', () => call('return_to_base'));
    shadow.getElementById('rc-btn-stop')  .addEventListener('click', () => call('stop'));
    shadow.getElementById('rc-btn-locate').addEventListener('click', () => call('locate'));
  }

  _update() {
    const hass   = this._hass;
    const cfg    = this._config;
    const shadow = this.shadowRoot;
    const vacuum = hass.states[cfg.entity];

    if (!vacuum) return;

    const state      = vacuum.state;
    const attrs      = vacuum.attributes || {};
    const info       = getStateInfo(state);
    const available  = state !== 'unavailable';

    // Connection dot
    shadow.getElementById('rc-dot').className     = 'rc-conn-dot' + (available ? '' : ' offline');
    shadow.getElementById('rc-conn-txt').textContent = available ? 'Connected' : 'Offline';

    // Ring + state label
    shadow.getElementById('rc-ring').className      = 'rc-ring rc-ring-active ' + (info.ring || '');
    const lbl = shadow.getElementById('rc-state-lbl');
    lbl.className   = 'rc-state-lbl ' + info.cls;
    lbl.textContent = info.label;

    // Battery
    const batEnt  = cfg.battery_entity ? hass.states[cfg.battery_entity] : null;
    const batPct  = batEnt ? parseInt(batEnt.state) : attrs.battery_level;
    const batEl   = shadow.getElementById('rc-bat-fill');
    if (batPct != null && !isNaN(batPct)) {
      shadow.getElementById('rc-bat-pct').textContent  = batPct + '%';
      batEl.style.width      = batPct + '%';
      batEl.style.background = batPct > 50
        ? 'var(--success-color, #1D9E75)'
        : batPct > 20
          ? 'var(--warning-color, #BA7517)'
          : 'var(--error-color, #E24B4A)';
    } else {
      shadow.getElementById('rc-bat-pct').textContent = '—';
    }

    // Mission time
    const mssnEnt = cfg.mission_time_entity ? hass.states[cfg.mission_time_entity] : null;
    shadow.getElementById('rc-mssn').textContent =
      mssnEnt ? mssnEnt.state : (attrs.mission_minutes ?? '—');

    // Sqft
    const areaEnt = cfg.area_entity ? hass.states[cfg.area_entity] : null;
    shadow.getElementById('rc-sqft').textContent =
      areaEnt ? areaEnt.state : (attrs.sqft_cleaned ?? '—');

    // Bin full
    const binEnt = cfg.bin_entity ? hass.states[cfg.bin_entity] : null;
    const binFull = binEnt ? binEnt.state === 'on' : attrs.bin_full;
    const binPill = shadow.getElementById('rc-bin-pill');
    binPill.className   = 'rc-pill ' + (binFull ? 'rc-pill-warn' : 'rc-pill-ok');
    binPill.textContent = binFull ? 'Bin Full' : 'Bin OK';

    // Stuck
    const stuckEnt = cfg.stuck_entity ? hass.states[cfg.stuck_entity] : null;
    const stuck    = stuckEnt ? stuckEnt.state === 'on' : state === 'error';
    const stuckPill = shadow.getElementById('rc-stuck-pill');
    stuckPill.className   = 'rc-pill ' + (stuck ? 'rc-pill-bad' : 'rc-pill-ok');
    stuckPill.textContent = stuck ? 'Stuck!' : 'Not Stuck';

    // Last command
    const lastCmd = attrs.last_command || '—';
    shadow.getElementById('rc-last-cmd').textContent = lastCmd;

    // Disable buttons when unavailable
    ['start','pause','dock','stop','locate'].forEach(id => {
      const btn = shadow.getElementById('rc-btn-' + id);
      if (btn) btn.disabled = !available;
    });
  }

  getCardSize() { return 4; }

  static getConfigElement() {
    return document.createElement('roomba-card-editor');
  }

  static getStubConfig() {
    return { entity: 'vacuum.roomba', name: 'Roomba' };
  }
}

customElements.define('roomba-card', RoombaCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type:        'roomba-card',
  name:        'Roomba Card',
  description: 'Control card for the ha-roomba-custom integration',
  preview:     false,
});
