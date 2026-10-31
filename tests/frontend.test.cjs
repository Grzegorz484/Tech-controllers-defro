/* Unit tests of the bundled card, without any connection to Home Assistant. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../custom_components/defro_emodul/www/defro-emodul-card.js'), 'utf8');

function setup() {
  const registry = new Map();
  class Element {
    attachShadow() {
      this.shadowRoot = {
        innerHTML: '', addEventListener() {}, querySelectorAll() { return []; },
        querySelector() { return {textContent: '', classList: {toggle() {}}}; },
      };
    }
  }
  const context = vm.createContext({
    HTMLElement: Element,
    CustomEvent,
    window: {confirm: () => true, setInterval: () => 1, clearInterval() {}},
    customElements: {get: (name) => registry.get(name), define: (name, value) => registry.set(name, value)},
  });
  vm.runInContext(source + '\nglobalThis.symbols = {clock, dayNames, escapeHtml};', context);
  const Card = registry.get('defro-emodul-card');
  return {card: new Card(), context, Card};
}

function configure(card, item) {
  card._selected = 'entry';
  card._controllers = [{entry_id: 'entry', online: true, name: 'DEFRO', controls: [item], tiles: []}];
  card._section = 'MU';
  const calls = [];
  card._hass = {
    async callWS(request) { calls.push(['read', request]); return {response: {controllers: card._controllers}}; },
    async callService(domain, service, data) { calls.push(['write', domain, service, data]); },
  };
  return calls;
}

function row(key, fields = {}) {
  const button = {disabled: false, isConnected: false};
  return {button, dataset: {key}, querySelector: (selector) => fields[selector],
    querySelectorAll: (selector) => fields[selector] || []};
}

test('registers one local custom card and renders semantic icons', () => {
  const {card, context, Card} = setup();
  assert.equal(context.window.customCards[0].type, 'defro-emodul-card');
  assert.equal(Card.getStubConfig().type, 'custom:defro-emodul-card');
  assert.match(card._icon('mdi:pump'), /mdi:pump/);
  assert.doesNotMatch(card._icon('x" onerror="alert(1)'), /onerror/);
});

test('escapes labels, choices and titles from external data', () => {
  const {card} = setup();
  const hostile = '<img src=x onerror="alert(1)">';
  configure(card, {key:'mu_1',section:'MU',kind:'select',available:true,
    label:hostile,name:hostile,icon:'mdi:pump',options:[{value:1,label:hostile}],value:1});
  card._config = {title:hostile};
  card._render();
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<img/);
  assert.match(card.shadowRoot.innerHTML, /&lt;img/);
});

test('uses Sunday-based API days and correct half-hour slot boundaries', () => {
  const {context} = setup();
  assert.equal(context.symbols.dayNames[0], 'Niedziela');
  assert.equal(context.symbols.dayNames[1], 'Poniedziałek');
  assert.equal(context.symbols.clock(0,48), '00:00');
  assert.equal(context.symbols.clock(47,48), '23:30');
  assert.equal(context.symbols.clock(23,24), '23:00');
});

test('48-bit schedules keep the first and last slots separate', () => {
  const {card} = setup();
  const html = card._editor({kind:'schedule_onoff',day:0,values:[1,...Array(46).fill(0),1]});
  assert.equal((html.match(/data-slot/g) || []).length, 48);
  assert.equal((html.match(/data-slot checked/g) || []).length, 2);
  assert.match(html, /Niedziela/);
  assert.match(html, /23:30/);
});

test('offset schedules expose 24 signed hourly fields and limits', () => {
  const {card} = setup();
  const html = card._editor({kind:'schedule_offset',day:1,min:-25,max:25,values:Array(24).fill(-2)});
  assert.equal((html.match(/data-slot/g) || []).length, 24);
  assert.match(html, /value="-2" min="-25" max="25"/);
});

test('reading the panel never sends a boiler command', async () => {
  const {card} = setup();
  const calls = configure(card, {key:'mu_1',name:'A',label:'A',section:'MU',kind:'action',available:true});
  await card._load(true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1].service, 'get_controls');
  assert.equal(calls[0][1].return_response, true);
});

test('overview tiles link to the actual HA entity, including renamed sensors', () => {
  const {card} = setup();
  const html = card._overview({tiles: [{entity_id:'sensor.moja_temperatura_kotla',
    name:'Temperatura CO',value:55.1,unit:'°C',icon:'mdi:radiator'}]});
  assert.match(html, /<button type="button" class="tile" data-action="more-info"/);
  assert.match(html, /data-entity-id="sensor.moja_temperatura_kotla"/);
  assert.match(html, /55\.1/);
  assert.match(html, /historię i szczegóły/);
});

test('clicking a tile opens native HA more-info without a boiler command', () => {
  const {card} = setup();
  const calls = configure(card, {key:'mu_1'});
  const events = [];
  card.dispatchEvent = (event) => events.push(event);
  const button = {disabled:false,dataset:{action:'more-info',entityId:'sensor.moja_temperatura_kotla'}};
  card._click({target:{closest:(selector)=>selector==='button[data-action]' ? button : null}});
  assert.equal(events.length, 1);
  assert.equal(events[0].type, 'hass-more-info');
  assert.equal(events[0].detail.entityId, 'sensor.moja_temperatura_kotla');
  assert.equal(events[0].bubbles, true);
  assert.equal(events[0].composed, true);
  assert.equal(calls.length, 0);
});

test('unavailable readings keep history links, missing registry entities are disabled', () => {
  const {card} = setup();
  const offline = card._tile({entity_id:'binary_sensor.pompa_co',name:'Pompa CO',value:null});
  assert.doesNotMatch(offline, /\sdisabled(?:\s|>)/);
  assert.match(offline, /data-entity-id="binary_sensor.pompa_co"/);
  const missing = card._tile({entity_id:null,name:'Brak encji',value:null});
  assert.match(missing, /\sdisabled\s/);
  const events = [];
  card.dispatchEvent = (event) => events.push(event);
  const button = {disabled:true,dataset:{action:'more-info',entityId:''}};
  card._click({target:{closest:(selector)=>selector==='button[data-action]' ? button : null}});
  assert.equal(events.length, 0);
});

test('only confirmed working devices receive the corresponding animation and label', () => {
  const {card} = setup();
  for (const animation of ['fan', 'pump', 'feed', 'heat', 'valve']) {
    const tile = {entity_id:'binary_sensor.device',name:'Urządzenie',icon:'mdi:pump',
      value:true,active:true,animation};
    const html = card._tile(tile);
    assert.match(html, new RegExp(`class="device-active device-${animation}"`));
    assert.match(html, /tile-activity">Pracuje/);
    assert.match(html, /data-entity-id="binary_sensor.device"/);
    for (const active of [false, null, undefined, 'true', 1]) {
      assert.doesNotMatch(card._tile({...tile,active}), /device-active|tile-activity/);
    }
    assert.doesNotMatch(card._tile({...tile,value:null}), /device-active|tile-activity/);
    assert.doesNotMatch(card._tile({...tile,value:undefined}), /device-active|tile-activity/);
  }
});

test('fan speed needs explicit activity and does not imply operation by itself', () => {
  const {card} = setup();
  const tile = {entity_id:'sensor.fan_speed',name:'Wentylator — bieg',icon:'mdi:fan',
    value:35,unit:'%',animation:'fan'};
  assert.doesNotMatch(card._tile(tile), /device-active|tile-activity/);
  assert.match(card._tile({...tile,active:true}), /device-fan/);
});

test('offline controllers and failed reads stop animation while keeping history available', async () => {
  const {card} = setup();
  const calls = configure(card, {key:'mu_1'});
  const tile = {entity_id:'binary_sensor.pump',name:'Pompa CO',icon:'mdi:pump',
    value:true,animation:'pump',active:true};
  card._controllers[0].tiles = [tile];
  assert.match(card._overview(card._controller()), /device-active/);
  assert.doesNotMatch(card._overview({...card._controller(),online:false}), /device-active|tile-activity/);
  card._hass.callWS = async () => { throw new Error('Brak połączenia'); };
  await card._load(true);
  assert.match(card._error, /Brak połączenia/);
  assert.doesNotMatch(card._tile(tile), /device-active|tile-activity/);
  assert.match(card._tile(tile), /data-entity-id="binary_sensor.pump"/);
  card._hass.callWS = async () => ({response:{controllers:card._controllers}});
  await card._load(true);
  assert.match(card._tile(tile), /device-active/);
  assert.equal(calls.length, 0);
});

test('animation metadata cannot inject attributes and menu icons remain static', () => {
  const {card} = setup();
  const hostile = 'fan" onmouseover="alert(1)';
  assert.doesNotMatch(card._icon('mdi:fan',hostile), /device-active|onmouseover/);
  assert.doesNotMatch(card._tile({value:true,active:true,animation:hostile}), /device-active|onmouseover/);
  assert.doesNotMatch(card._row({key:'mu_1',name:'Pompa',label:'Pompa',icon:'mdi:pump',
    kind:'switch',available:true,value:true,active:true,animation:'pump'}), /device-active/);
});

test('reduced motion disables animation and retains a visible working indicator', () => {
  const {card,Card} = setup();
  assert.match(Card.styles, /@media\(prefers-reduced-motion:reduce\)\{\.tile ha-icon\.device-active\{animation:none\}\}/);
  assert.match(card._tile({icon:'mdi:pump',value:true,active:true,animation:'pump'}), /tile-activity">Pracuje/);
});

test('polling preserves unfinished form contents', async () => {
  const {card} = setup();
  configure(card, {key:'mu_1'});
  card._dirty.add('mu_1');
  card.shadowRoot.innerHTML = 'unfinished form';
  await card._load(true);
  assert.equal(card.shadowRoot.innerHTML, 'unfinished form');
});

test('canceling a dialogue sends no command', async () => {
  const {card,context} = setup();
  const calls = configure(card,{key:'mu_1',kind:'action',available:true,label:'Reset',message:'Potwierdź'});
  context.window.confirm = () => false;
  const form = row('mu_1');
  await card._save(form,form.button);
  assert.equal(calls.length,0);
});

test('confirmed actions send the explicit confirmation flag once', async () => {
  const {card} = setup();
  const calls = configure(card,{key:'mu_1',name:'A',section:'MU',kind:'action',available:true,label:'Rozpalanie',message:'Potwierdź'});
  const form = row('mu_1');
  await card._save(form,form.button);
  const writes = calls.filter((call)=>call[0]==='write');
  assert.equal(writes.length,1);
  assert.equal(JSON.stringify(writes[0][3]),JSON.stringify({entry_id:'entry',key:'mu_1',value:true,confirm:true}));
});

test('curve editor sends all point values in API order', async () => {
  const {card} = setup();
  const calls = configure(card,{key:'mi_1',name:'Krzywa',label:'Krzywa',section:'MI',kind:'curve',available:true});
  const form = row('mi_1',{'[data-slot]':[{value:'65'},{value:'55'},{value:'50'},{value:'45'}]});
  await card._save(form,form.button);
  const write = calls.find((call)=>call[0]==='write');
  assert.equal(JSON.stringify(write[3].value),'[65,55,50,45]');
  assert.equal(write[3].confirm,false);
});

test('locked settings cannot be saved', async () => {
  const {card} = setup();
  const calls=configure(card,{key:'mu_1',kind:'number',available:false});
  const form=row('mu_1');
  await card._save(form,form.button);
  assert.equal(calls.length,0);
});

test('known submenu codes use only the unlock service and clear the input', async () => {
  const {card}=setup();
  const calls=configure(card,{key:'ms_35',name:'Menu',label:'Menu',section:'MS',kind:'password',can_unlock:true});
  const input={value:'5678',reportValidity:()=>true};
  const form=row('ms_35',{'[data-code]':input});
  await card._unlock(form,form.button);
  const writes=calls.filter((c)=>c[0]==='write');
  assert.equal(writes.length,1);
  assert.equal(writes[0][2],'unlock_menu');
  assert.equal(writes[0][3].code,'5678');
  assert.equal(input.value,'');
});
