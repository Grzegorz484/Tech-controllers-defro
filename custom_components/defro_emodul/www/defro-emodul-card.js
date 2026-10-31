/* DEFRO eModuł menu card. MIT. No external scripts or credentials in the UI. */
const escapeHtml = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));
const dayNames = ["Niedziela", "Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Poniedziałek–piątek", "Sobota–niedziela", "Cały tydzień"];
const sectionNames = {overview: "Podgląd", MU: "Użytkownik", MI: "Instalator", MS: "Serwis", MP: "Producent"};
const deviceAnimations = new Set(["fan", "pump", "feed", "heat", "valve"]);
const reasons = {
  controller_offline: "Sterownik jest odłączony", access_denied: "Brak dostępu lub nieaktywna gałąź",
  value_updating: "Oczekiwanie na potwierdzenie zmiany", parameters_missing: "Brak danych ustawienia",
  invalid_metadata: "API nie podało poprawnego zakresu lub formatu", password: "Menu chronione kodem",
  menu_locked: "Podaj znany kod w konfiguracji integracji", unsupported: "Nieobsługiwany typ elementu",
  cloud_unavailable: "Brak aktualnego odczytu z eModułu",
  information_only: "Komunikat informacyjny", group: "Grupa ustawień",
};
const clock = (index, slots) => {
  const mins = index * (1440 / slots);
  return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
};

class DefroEmodulCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._section = "overview";
    this._dirty = new Set();
    this._query = "";
    this._showUnavailable = true;
    this._controllers = [];
    this.shadowRoot.addEventListener("click", (event) => this._click(event));
    this.shadowRoot.addEventListener("input", (event) => this._input(event));
    this.shadowRoot.addEventListener("change", (event) => this._change(event));
  }

  static getStubConfig() { return {type: "custom:defro-emodul-card", title: "DEFRO eModuł"}; }
  setConfig(config) { this._config = {...config}; if (this._hass) this._load(true); }
  set hass(hass) {
    this._hass = hass;
    if (this.isConnected && !this._lastFetch) this._load();
  }
  getCardSize() { return this._section === "overview" ? 5 : 12; }
  connectedCallback() {
    this._render();
    this._load();
    this._timer = window.setInterval(() => this._load(), 10000);
  }
  disconnectedCallback() { window.clearInterval(this._timer); }

  async _load(force = false) {
    if (!this._hass || this._loading || (!force && Date.now() - (this._lastFetch || 0) < 9000)) return;
    this._loading = true;
    try {
      const result = await this._hass.callWS({
        type: "call_service", domain: "defro_emodul", service: "get_controls", return_response: true,
        service_data: this._config?.entry_id ? {entry_id: this._config.entry_id} : {},
      });
      this._controllers = result.response?.controllers || [];
      this._lastFetch = Date.now();
      if (!this._controllers.some((c) => c.entry_id === this._selected)) this._selected = this._controllers[0]?.entry_id;
      this._error = "";
    } catch (error) {
      this._error = error.message || "Nie udało się pobrać ustawień. Panel wymaga konta administratora HA.";
    } finally {
      this._loading = false;
      if (!this._dirty.size && !this._busy) this._render();
    }
  }

  _controller() { return this._controllers.find((c) => c.entry_id === this._selected); }
  _icon(icon, animation = "") {
    const activity = deviceAnimations.has(animation) ? ` class="device-active device-${animation}"` : "";
    return `<ha-icon icon="${escapeHtml(/^mdi:[a-z0-9-]+$/.test(icon) ? icon : "mdi:tune")}"${activity} aria-hidden="true"></ha-icon>`;
  }
  _input(event) {
    if (event.target.dataset.search !== undefined) {
      this._query = event.target.value;
      this._filter();
      return;
    }
    const row = event.target.closest("[data-key]");
    if (row) {
      this._dirty.add(row.dataset.key);
      row.classList.add("edited");
      this._status("Masz niezapisane zmiany. Użyj przycisku Zapisz przy ustawieniu.");
    }
  }
  _change(event) {
    if (event.target.dataset.controller !== undefined) {
      if (!this._discard()) { event.target.value = this._selected; return; }
      this._selected = event.target.value;
      this._render();
    } else if (event.target.dataset.unavailable !== undefined) {
      this._showUnavailable = event.target.checked;
      this._filter();
    } else this._input(event);
  }
  _discard() {
    if (this._dirty.size && !window.confirm("Porzucić niezapisane zmiany formularzy?")) return false;
    this._dirty.clear();
    return true;
  }
  _status(text, error = false) {
    const node = this.shadowRoot.querySelector(".status");
    if (node) { node.textContent = text; node.classList.toggle("error", error); }
  }
  _filter() {
    const query = this._query.toLocaleLowerCase("pl");
    for (const row of this.shadowRoot.querySelectorAll("[data-key]")) {
      row.hidden = (!this._showUnavailable && row.dataset.available !== "true") || !row.dataset.searchText.includes(query);
    }
  }
  _click(event) {
    const tab = event.target.closest("[data-tab]");
    if (tab) {
      if (this._discard()) { this._section = tab.dataset.tab; this._render(); }
      return;
    }
    const button = event.target.closest("button[data-action]");
    if (!button || button.disabled) return;
    if (button.dataset.action === "more-info") {
      const entityId = button.dataset.entityId;
      if (entityId) this.dispatchEvent(new CustomEvent("hass-more-info", {
        detail: {entityId}, bubbles: true, composed: true,
      }));
      return;
    }
    if (button.dataset.action === "refresh") { this._load(true); return; }
    const row = button.closest("[data-key]");
    if (!row) return;
    if (button.dataset.action === "cancel") {
      this._dirty.delete(row.dataset.key);
      // Render only this row so other unfinished forms keep their values.
      const control = this._controller()?.controls.find((i) => i.key === row.dataset.key);
      if (control) row.outerHTML = this._row(control);
      return;
    }
    if (button.dataset.action === "fill") {
      const source = row.querySelector("[data-fill-value]");
      if (source && !source.reportValidity()) return;
      for (const input of row.querySelectorAll("[data-slot]")) {
        if (input.type === "checkbox") input.checked = button.dataset.fill === "1";
        else input.value = source.value;
      }
      this._dirty.add(row.dataset.key); row.classList.add("edited");
      return;
    }
    if (button.dataset.action === "save") this._save(row, button);
    if (button.dataset.action === "unlock") this._unlock(row, button);
  }

  async _unlock(row, button) {
    if (this._busy) return;
    const controller = this._controller();
    const item = controller?.controls.find((i) => i.key === row.dataset.key);
    const input = row.querySelector("[data-code]");
    if (!item?.can_unlock || !input?.reportValidity()) return;
    this._busy = item.key; button.disabled = true;
    try {
      await this._hass.callService("defro_emodul", "unlock_menu", {
        entry_id: controller.entry_id, key: item.key, code: input.value,
      });
      input.value = "";
      this._dirty.delete(item.key);
      this._busy = null;
      await this._load(true);
      this._status("Kod został przyjęty. Menu zostało odświeżone.");
    } catch (error) {
      input.value = "";
      this._status(error.message || "Kod nie został przyjęty.", true);
    } finally { this._busy = null; if (button.isConnected) button.disabled = false; }
  }

  async _save(row, button) {
    if (this._busy) return;
    const controller = this._controller();
    const item = controller?.controls.find((i) => i.key === row.dataset.key);
    if (!item?.available) return;
    for (const input of row.querySelectorAll("input,select")) if (!input.reportValidity()) return;
    let value;
    if (item.kind === "number") value = Number(row.querySelector("[data-value]").value);
    else if (item.kind === "switch") value = row.querySelector("[data-value]").checked;
    else if (item.kind === "select") value = row.querySelector("[data-value]").value;
    else if (["checkbox", "schedule_onoff"].includes(item.kind)) value = [...row.querySelectorAll("[data-slot]")].map((input) => Number(input.checked));
    else if (["curve", "schedule_offset"].includes(item.kind)) value = [...row.querySelectorAll("[data-slot]")].map((input) => Number(input.value));
    else if (item.kind === "action") {
      if (!window.confirm(`${item.label}\n\n${item.message}\n\nWykonać tę czynność na sterowniku?`)) return;
      value = true;
    } else return;
    this._busy = item.key; button.disabled = true;
    this._status("Wysyłanie zmiany do eModułu…");
    try {
      await this._hass.callService("defro_emodul", "set_parameter", {
        entry_id: controller.entry_id, key: item.key, value, confirm: item.kind === "action",
      });
      this._dirty.delete(item.key);
      this._busy = null;
      await this._load(true);
      if (this._dirty.size) {
        row.querySelector("fieldset").disabled = true;
        button.disabled = true;
      }
      this._status("eModuł przyjął polecenie. Oczekiwanie na potwierdzenie odczytem sterownika.");
    } catch (error) {
      this._status(error.message || "Nie potwierdzono zapisu. Sprawdź aktualny stan przed kolejną próbą.", true);
    } finally { this._busy = null; if (button.isConnected) button.disabled = false; }
  }

  _number(value, min, max, step = 1, attr = "data-value") {
    return `<input type="number" ${attr} required value="${escapeHtml(value)}" min="${escapeHtml(min)}" max="${escapeHtml(max)}" step="${escapeHtml(step)}">`;
  }
  _editor(item) {
    const e = escapeHtml;
    switch (item.kind) {
      case "number": return `<div class="value-line">${this._number(item.value, item.min, item.max, item.step)}<span>${e(item.unit)}</span><small>${e(item.min)} – ${e(item.max)} · krok ${e(item.step)}</small></div>`;
      case "switch": return `<label class="toggle"><input type="checkbox" data-value ${item.value ? "checked" : ""}> Włączone</label>`;
      case "select": return `<select data-value aria-label="${e(item.label)}">${(item.options || []).map((o) => `<option ${o.value === item.value ? "selected" : ""}>${e(o.label)}</option>`).join("")}</select>`;
      case "checkbox": return `<div class="checks">${(item.options || []).map((o) => `<label><input type="checkbox" data-slot ${(Math.floor(item.value / 2 ** o.index) % 2) ? "checked" : ""}>${e(o.label)}</label>`).join("")}</div>`;
      case "curve": return `<p class="hint">Temperatura zadana w zależności od temperatury zewnętrznej.</p><div class="curve">${(item.points || []).map((p) => `<label>Przy ${e(p.position)} °C${this._number(p.value, item.min, item.max, 1, "data-slot")} °C</label>`).join("")}</div>`;
      case "schedule_offset": return `<p class="hint">${dayNames[item.day] || "Harmonogram dobowy"} · korekta nastawy (°C) co godzinę.</p><div class="fill">${this._number(0, item.min, item.max, 1, "data-fill-value aria-label=\"Korekta dla całej doby\"")}<button type="button" data-action="fill">Ustaw całą dobę</button></div><div class="slots">${(item.values || []).map((v, n) => `<label>${clock(n, 24)}${this._number(v, item.min, item.max, 1, "data-slot")}</label>`).join("")}</div>`;
      case "schedule_onoff": return `<p class="hint">${dayNames[item.day] || "Harmonogram dobowy"} · ${item.values?.length === 48 ? "przedziały 30 minut" : "przedziały godzinne"}</p><div class="fill"><button type="button" data-action="fill" data-fill="1">Włącz całą dobę</button><button type="button" data-action="fill" data-fill="0">Wyłącz całą dobę</button></div><div class="slots onoff">${(item.values || []).map((v, n) => `<label><input type="checkbox" data-slot ${v ? "checked" : ""}>${clock(n, item.values.length)}</label>`).join("")}</div>`;
      case "action": return `<p>${e(item.message)}</p><p class="hint">Przycisk poprosi o potwierdzenie przed wysłaniem polecenia.</p>`;
      case "password": return `<p class="hint">Podaj znany kod tej pozycji. Zostanie zapisany w lokalnej konfiguracji integracji. Kody głównych menu możesz też zmienić w ustawieniach integracji.</p><input type="password" data-code required pattern="[0-9]{1,16}" inputmode="numeric" autocomplete="off" aria-label="Kod menu"><button type="button" data-action="unlock">Odblokuj menu</button>`;
      default: return "";
    }
  }
  _row(item) {
    const e = escapeHtml;
    const unavailable = !item.available;
    return `<article data-key="${e(item.key)}" data-available="${!!item.available}" data-search-text="${e(item.name.toLocaleLowerCase("pl"))}" class="setting ${unavailable ? "unavailable" : ""}">
      <div class="setting-head">${this._icon(item.icon)}<div><strong>${e(item.label)}</strong><div class="path">${e(item.name)}</div></div></div>
      ${unavailable ? `<div class="reason">${e(reasons[item.reason] || item.reason)}</div>` : ""}
      ${item.warning ? `<p class="warning">${e(item.warning)}</p>` : ""}
      <fieldset ${unavailable && !item.can_unlock ? "disabled" : ""}>${this._editor(item)}${!["group", "password", "unsupported"].includes(item.kind) ? `<div class="buttons"><button type="button" data-action="save" class="primary">${item.kind === "action" ? "Wykonaj…" : "Zapisz"}</button><button type="button" data-action="cancel">Cofnij zmiany formularza</button></div>` : ""}</fieldset></article>`;
  }
  _tile(tile, online = true) {
    const e = escapeHtml;
    const entityId = tile.entity_id || "";
    const animation = online && !this._error && tile.value != null && tile.active === true && deviceAnimations.has(tile.animation) ? tile.animation : "";
    return `<button type="button" class="tile" data-action="more-info" data-entity-id="${e(entityId)}" ${entityId ? 'title="Historia i szczegóły w Home Assistant"' : 'disabled title="Brak encji w rejestrze Home Assistant"'}><span class="tile-icon">${this._icon(tile.icon, animation)}${animation ? '<span class="tile-activity">Pracuje</span>' : ""}</span><span class="tile-name">${e(tile.name)}</span><strong>${tile.value == null ? "—" : e(typeof tile.value === "boolean" ? (tile.value ? "Włączone" : "Wyłączone") : tile.value)} <small>${e(tile.unit)}</small></strong></button>`;
  }
  _overview(controller) {
    return `<div class="tiles">${(controller?.tiles || []).map((tile) => this._tile(tile, controller.online === true)).join("")}</div><p class="hint">Ruch ikony i oznaczenie „Pracuje” wskazują aktywny odczyt pracy urządzenia. Kliknij kafelek, aby otworzyć historię i szczegóły encji w Home Assistant. Wybierz menu powyżej, aby zmieniać nastawy. Odczyty są aktualizowane przez integrację; menu standardowo co 5 minut. Przed zapisem uprawnienia i zakres są sprawdzane ponownie.</p>`;
  }
  _render() {
    const controller = this._controller();
    const menu = controller?.controls || [];
    const sections = ["overview", ...Object.keys(sectionNames).filter((s) => s !== "overview" && menu.some((i) => i.section === s))];
    if (!sections.includes(this._section)) this._section = "overview";
    const items = menu.filter((i) => i.section === this._section && i.kind !== "group");
    this.shadowRoot.innerHTML = `<style>${DefroEmodulCard.styles}</style><ha-card>
      <header><div>${this._icon("mdi:fire")}<span>${escapeHtml(this._config?.title || "DEFRO eModuł")}</span></div><span class="online ${controller?.online ? "yes" : ""}">${controller ? (controller.online ? "Połączony" : "Odłączony") : "Ładowanie…"}</span></header>
      <div class="body">${this._controllers.length > 1 ? `<select data-controller aria-label="Sterownik">${this._controllers.map((c) => `<option value="${escapeHtml(c.entry_id)}" ${c.entry_id === this._selected ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}</select>` : ""}
      <nav aria-label="Menu sterownika">${sections.map((s) => `<button type="button" data-tab="${s}" class="${s === this._section ? "active" : ""}">${escapeHtml(sectionNames[s])}</button>`).join("")}</nav>
      <div class="status ${this._error ? "error" : ""}" role="status" aria-live="polite">${escapeHtml(this._error || "")}</div>
      ${!controller ? `<p>${this._error ? "Sprawdź, czy integracja jest uruchomiona i korzystasz z konta administratora HA." : "Oczekiwanie na uruchomioną integrację DEFRO eModuł…"}</p><button data-action="refresh">Odśwież panel</button>` : this._section === "overview" ? this._overview(controller) : `<div class="filters"><input type="search" data-search placeholder="Szukaj ustawienia…" aria-label="Szukaj ustawienia" value="${escapeHtml(this._query)}"><label><input type="checkbox" data-unavailable ${this._showUnavailable ? "checked" : ""}>Pokaż niedostępne</label><span>${items.length} pozycji</span></div><div class="settings">${items.map((i) => this._row(i)).join("") || "Brak ustawień udostępnionych w tym menu."}</div>`}
      </div></ha-card>`;
    this._filter();
  }

  static styles = `
    :host{display:block;color:var(--primary-text-color,#17202b);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
    *{box-sizing:border-box}ha-card{display:block;overflow:hidden;background:var(--card-background-color,#fff);border-radius:16px;border:1px solid var(--divider-color,#e3e6ea)}
    header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:20px;background:linear-gradient(120deg,#293748,#182331);color:white}
    header>div{display:flex;align-items:center;gap:10px;font-size:21px;font-weight:650}header ha-icon{color:#ffa54c;--mdc-icon-size:30px}.online{font-size:12px;color:#ffd09f}.online.yes{color:#a9e9c2}
    .body{padding:16px}nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}button,input,select{font:inherit}button{cursor:pointer;border:1px solid var(--divider-color,#d5dce4);border-radius:8px;padding:9px 12px;color:var(--primary-text-color,#263449);background:var(--secondary-background-color,#f5f7fa)}button:hover{filter:brightness(.96)}button:disabled{cursor:default;opacity:.5}button.active,button.primary{background:#e77e21;color:#fff;border-color:#e77e21}
    input[type=number],input[type=search],select{background:var(--card-background-color,#fff);color:inherit;border:1px solid var(--divider-color,#cbd3dd);border-radius:7px;padding:9px;min-width:0}input[type=checkbox]{width:20px;height:20px;accent-color:#e77e21;vertical-align:middle;flex-shrink:0}input[type=number]{width:110px}input[type=search]{width:min(100%,320px)}select{max-width:100%}input:focus-visible,button:focus-visible,select:focus-visible{outline:2px solid #e77e21;outline-offset:2px}
    .filters{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:16px 0}.filters label{font-size:13px}.filters>span{font-size:12px;color:var(--secondary-text-color,#6d7580)}.status:empty{display:none}.status{padding:10px 12px;margin:10px 0;background:var(--secondary-background-color,#f1f5f8);border-radius:8px;font-size:13px}.status.error,.warning{color:var(--error-color,#b3261e)}
    .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}.tile{padding:16px 12px;border:1px solid var(--divider-color,#e0e6eb);border-radius:12px;background:var(--card-background-color,#fff);color:inherit;text-align:left;min-width:0}.tile:disabled{opacity:1}.tile ha-icon{color:#e77e21;--mdc-icon-size:29px}.tile ha-icon[icon="mdi:water-boiler"],.tile ha-icon[icon="mdi:valve"]{color:#398dd4}.tile ha-icon[icon="mdi:pump"]{color:#43946b}.tile ha-icon[icon="mdi:fan"]{color:#7c8d9e}.tile-name{display:block;font-size:12px;color:var(--secondary-text-color,#637083);margin:9px 0}.tile strong{display:block;font-size:21px}.tile small{font-weight:400;font-size:13px}
    .tile-icon{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:32px}.tile-activity{font-size:10px;font-weight:600;color:var(--primary-text-color,#263449);background:var(--secondary-background-color,#f5f7fa);border:1px solid var(--divider-color,#d5dce4);border-radius:12px;padding:3px 6px}.tile ha-icon.device-active{color:var(--state-active-color,#e77e21);filter:drop-shadow(0 0 4px currentColor);transform-origin:center;display:inline-block}.device-fan{animation:defro-spin 1.2s linear infinite}.device-pump{animation:defro-pump 1.1s ease-in-out infinite}.device-feed{animation:defro-feed .7s ease-in-out infinite}.device-heat{animation:defro-heat 1.8s ease-in-out infinite}.device-valve{animation:defro-valve 1.6s ease-in-out infinite}
    @keyframes defro-spin{to{transform:rotate(360deg)}}@keyframes defro-pump{0%,100%{transform:scale(1)}50%{transform:scale(1.14)}}@keyframes defro-feed{0%,100%{transform:translateX(-2px)}50%{transform:translateX(2px)}}@keyframes defro-heat{0%,100%{opacity:.65}50%{opacity:1}}@keyframes defro-valve{0%,100%{transform:rotate(-12deg)}50%{transform:rotate(12deg)}}
    @media(prefers-reduced-motion:reduce){.tile ha-icon.device-active{animation:none}}
    .setting{border:1px solid var(--divider-color,#dce2e8);border-radius:12px;padding:16px;margin-bottom:10px}.setting.edited{border-color:#e77e21}.setting[hidden]{display:none}.setting-head{display:flex;align-items:flex-start;gap:10px}.setting-head ha-icon{color:#e77e21;flex-shrink:0}.setting-head strong{font-size:15px}.path{font-size:11px;color:var(--secondary-text-color,#6d7580);margin-top:4px;overflow-wrap:anywhere}.reason{font-size:12px;color:var(--secondary-text-color,#6d7580);margin-top:10px}.unavailable .setting-head ha-icon{color:var(--disabled-text-color,#8b95a0)}
    fieldset{border:0;padding:0;margin:12px 0 0;min-width:0}fieldset:disabled{opacity:.6}.value-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.value-line small{color:var(--secondary-text-color,#6d7580);font-size:12px}.buttons{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}.buttons button:last-child{font-size:12px}.toggle,.checks label{display:flex;gap:8px;align-items:center}.checks{display:flex;gap:14px;flex-wrap:wrap}.hint{font-size:12px;line-height:1.6;color:var(--secondary-text-color,#6d7580)}
    .curve{display:flex;gap:12px;flex-wrap:wrap}.curve label{display:flex;align-items:center;gap:6px;flex-direction:column;font-size:12px}.slots{display:grid;grid-template-columns:repeat(auto-fit,minmax(74px,1fr));gap:8px;margin-top:12px}.slots label{font-size:11px;text-align:center;display:flex;align-items:center;flex-direction:column;gap:5px}.slots input[type=number]{width:100%;max-width:100px;padding:8px 4px}.slots.onoff label{border:1px solid var(--divider-color,#dce2e8);border-radius:6px;padding:8px}.slots.onoff label:has(input:checked){background:#e77e211a;border-color:#e77e21}.fill{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.fill button{font-size:12px}code{overflow-wrap:anywhere}p{line-height:1.5;font-size:13px}
    @media(max-width:440px){.body{padding:10px}header{padding:16px}header>div{font-size:18px}.setting{padding:12px}.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}nav button{padding:8px;font-size:12px}.slots{grid-template-columns:repeat(4,minmax(0,1fr))}.online{font-size:10px}}
  `;
}

if (!customElements.get("defro-emodul-card")) customElements.define("defro-emodul-card", DefroEmodulCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "defro-emodul-card")) window.customCards.push({
  type: "defro-emodul-card", name: "DEFRO eModuł", description: "Podgląd, nastawy i pełne menu DEFRO z ikonami", preview: true,
});
