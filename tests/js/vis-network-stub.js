/* A tiny stand-in for vis-network, used only by tests/test_viewer_runtime.js.
   It implements the handful of DataSet/Network members the viewer actually
   calls, so the interaction logic (expand, collapse, search, path) can be
   exercised in jsdom without a browser or a CDN. */
(function (global) {
  function DataSet(items) {
    this._items = new Map();
    (items || []).forEach(function (item) { this._items.set(item.id, Object.assign({}, item)); }, this);
  }
  DataSet.prototype.add = function (items) {
    (Array.isArray(items) ? items : [items]).forEach(function (item) {
      this._items.set(item.id, Object.assign({}, item));
    }, this);
  };
  DataSet.prototype.update = function (items) {
    (Array.isArray(items) ? items : [items]).forEach(function (item) {
      var existing = this._items.get(item.id) || {};
      this._items.set(item.id, Object.assign(existing, item));
    }, this);
  };
  DataSet.prototype.remove = function (ids) {
    (Array.isArray(ids) ? ids : [ids]).forEach(function (id) { this._items.delete(id); }, this);
  };
  DataSet.prototype.get = function (id) {
    if (id === undefined) return Array.from(this._items.values());
    return this._items.get(id) || null;
  };
  DataSet.prototype.forEach = function (fn) {
    Array.from(this._items.values()).forEach(function (item) { fn(item); });
  };
  Object.defineProperty(DataSet.prototype, "length", {
    get: function () { return this._items.size; }
  });

  function Network(container, data, options) {
    this.body = data;
    this.options = options;
    this._handlers = {};
    this._scale = 1;
    this.lastFocus = null;
    this.lastFit = null;
    var self = this;
    setTimeout(function () { self.emit("stabilizationIterationsDone"); }, 0);
  }
  Network.prototype.on = function (event, fn) {
    (this._handlers[event] = this._handlers[event] || []).push(fn);
  };
  Network.prototype.once = Network.prototype.on;
  Network.prototype.emit = function (event, params) {
    (this._handlers[event] || []).forEach(function (fn) { fn(params); });
  };
  Network.prototype.getPositions = function (ids) {
    var out = {};
    (ids || []).forEach(function (id, i) { out[id] = {x: i * 40, y: i * 40}; });
    return out;
  };
  Network.prototype.fit = function (opts) { this.lastFit = opts || {}; };
  Network.prototype.focus = function (id, opts) { this.lastFocus = {id: id, opts: opts}; };
  Network.prototype.moveTo = function (opts) { if (opts && opts.scale) this._scale = opts.scale; };
  Network.prototype.getScale = function () { return this._scale; };
  Network.prototype.setOptions = function (opts) { Object.assign(this.options, opts); };
  Network.prototype.selectNodes = function (ids) { this.selected = ids; };
  Network.prototype.stabilize = function () { this.emit("stabilizationIterationsDone"); };

  global.vis = {DataSet: DataSet, Network: Network};
  global.__visStub = true;
})(typeof window !== "undefined" ? window : globalThis);
