/* No Cinnamon desktop is mutated: the applet runs with minimal API mocks. */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
let processStarts = 0;
const settingsSchema = JSON.parse(fs.readFileSync('src/settings-schema.json', 'utf8'));
let callback, killed = false, finalized = false, nextTimer = 1;
const timers = new Map(), removedTimers = new Set();
class Actor {
    constructor(props = {}) { assert(!('can_focus' in props)); Object.assign(this, props); }
    add_actor() {}
    set_child() {}
    set_policy() {}
    addActor() {}
    add_style_class_name() {}
}
class Menu {
    addActor() {}
    addMenuItem() {}
    removeAll() {}
    toggle() {}
    destroy() { this.destroyed = true; }
}
const subprocess = {
    communicate_utf8_async(a, b, cb) { callback = cb; },
    communicate_utf8_finish() { return [true, JSON.stringify(data), '']; },
    get_successful() { return true; },
    force_exit() { killed = true; }
};
const totals = {total_tokens: 1000, input_tokens: 900, cached_input_tokens: 450, output_tokens: 100, reasoning_output_tokens: 10, sessions: 1, cache_percent: 50};
const data = {schema_version: 1, available: true, updated_at: Date.now()/1000, today: totals, week: totals, month: totals, limits: null};
const context = {
    imports: {
        ui: {
            applet: {
                TextIconApplet: class {
                    constructor() {
                        this._applet_icon_box = new Actor();
                        this._applet_label = new Actor();
                    }
                    setAllowedLayout() {}
                    set_applet_icon_path(value) { this.iconPath = value; }
                    set_applet_label(value) { this.label = value; }
                    set_applet_tooltip(value) { this.tooltip = value; }
                }, AllowedLayout: {HORIZONTAL: 0}, AppletPopupMenu: Menu
            },
            popupMenu: {PopupMenuManager: class { addMenu() {} }, PopupBaseMenuItem: Actor, PopupMenuSection: Menu},
            settings: {AppletSettings: class {
                constructor(owner) { this.owner = owner; this.bindings = {}; }
                bind(key, property, onChange) {
                    this.bindings[key] = {property, onChange};
                    this.owner[property] = settingsSchema[key].default;
                }
                change(key, value) {
                    const binding = this.bindings[key];
                    this.owner[binding.property] = value;
                    binding.onChange();
                }
                finalize() { finalized = true; }
            }}
        },
        mainloop: {
            timeout_add_seconds(delay, fn) { const id = nextTimer++; timers.set(id, fn); return id; },
            timeout_add(delay, fn) { const id = nextTimer++; timers.set(id, fn); return id; },
            source_remove(id) { removedTimers.add(id); timers.delete(id); }
        },
        gi: {
            St: {BoxLayout: Actor, Bin: Actor, Label: Actor, ScrollView: Actor, PolicyType: {NEVER: 0, AUTOMATIC: 1}, Align: {START: 0}},
            Gio: {Subprocess: {new() { processStarts++; return subprocess; }}, SubprocessFlags: {STDOUT_PIPE: 1, STDERR_SILENCE: 2}},
            GLib: {build_filenamev(parts) { return parts.join('/'); }}
        }
    }, console
};
vm.createContext(context);
context.mockNow = 1800000000000;
vm.runInContext('Date.now = () => mockNow', context);
vm.runInContext(fs.readFileSync('src/applet.js', 'utf8'), context);
const applet = context.main({path: '/mock', uuid: 'codex-usage@pila'}, 0, 25, 1);
assert.equal(applet.iconPath, '/mock/icons/openai-codex-logo-symbolic.png');
assert.equal(applet.label, '5h — · W —');
assert.equal(applet.displayMode, 'limits');
assert.equal(settingsSchema['display-mode'].type, 'combobox');
assert.deepEqual(settingsSchema['display-mode'].options, {'Rate limits': 'limits', 'Daily tokens': 'tokens'});
callback(subprocess, {});
assert.equal(applet.label, '5h — · W —');
const now = context.mockNow/1000;
const limits = {observed_at: now, primary: {used_percent: 73, resets_at: now+3600}, secondary: {used_percent: 41, resets_at: now+3600}};
applet._data.limits = limits;
applet._render();
assert.equal(applet.label, '5h 73% · W 41%');
assert(applet.tooltip.includes('USED'));
const deadlineTimer = applet._deadlineTimer;
const startsBeforeReset = processStarts;
context.mockNow = limits.primary.resets_at * 1000;
assert.strictEqual(timers.get(deadlineTimer)(), false);
assert.equal(applet.label, '5h — · W —');
assert.equal(processStarts, startsBeforeReset + 1, 'Reset deadline must trigger a refresh');
callback(subprocess, {});
context.mockNow = now * 1000;
applet._data.limits = limits;
limits.primary.resets_at = now+3600;
limits.secondary.resets_at = now+7200;
applet._render();
limits.primary.stale = true;
applet._render();
assert.equal(applet.label, '5h 73%* · W 41%');
assert(applet.tooltip.includes('last observed'));
delete limits.primary.stale;
limits.primary.resets_at = 0;
applet._render();
assert.equal(applet.label, '5h — · W 41%');
limits.primary.resets_at = now+3600;
limits.observed_at = now-301;
applet._render();
assert.equal(applet.label, '5h 73%* · W 41%*');
limits.observed_at = now;
const primary = limits.primary;
limits.primary = null;
applet._render();
assert.equal(applet.label, '5h — · W 41%');
limits.primary = {used_percent: 'unexpected'};
applet._render();
assert.equal(applet.label, '5h — · W 41%');
limits.primary = primary;
const beforeSwitch = processStarts;
applet.settings.change('display-mode', 'tokens');
assert.equal(applet.label, '1K today');
applet.settings.change('display-mode', 'limits');
assert.equal(applet.label, '5h 73% · W 41%');
assert.equal(processStarts, beforeSwitch, 'Display changes must not run the collector');
applet._refresh();
subprocess.communicate_utf8_finish = () => { throw Error('Do not display this'); };
callback(subprocess, {});
assert.equal(applet.label, '5h 73%* · W 41%*');
assert(!applet.tooltip.includes('Do not display this'));
applet.settings.change('display-mode', 'tokens');
assert.equal(applet.label, '1K* today');
assert(applet.tooltip.includes('refresh failed'));
applet._data = null;
applet._render();
assert.equal(applet.label, '— today');
applet.settings.change('display-mode', 'limits');
assert.equal(applet.label, '5h — · W —');
applet._data = data;
applet._data.limits = limits;
limits.primary.resets_at = now+3600;
limits.secondary.resets_at = now+7200;
applet._failed = false;
applet._render();
const finalDeadlineTimer = applet._deadlineTimer;
applet._refresh();
applet.on_applet_removed_from_panel();
assert(killed && removedTimers.has(finalDeadlineTimer) && finalized && applet.menu.destroyed);
callback(subprocess, {});
console.log('Applet display settings, missing/stale/error states and lifecycle checks passed.');
