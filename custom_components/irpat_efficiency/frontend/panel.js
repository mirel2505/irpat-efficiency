// Initial dependency-free custom element; local assets only.
// User-defined labels are inserted through textContent, not HTML.
class IrpatEfficiencyPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.entries = [];
    this.error = false;
    this.loaded = false;
    this.busy = false;
  }

  set hass(value) {
    this._hass = value;
    if (!this.loaded && !this.busy && this.isConnected && value) this.refresh();
  }

  connectedCallback() {
    this.render();
    if (this._hass && !this.loaded && !this.busy) this.refresh();
  }

  async refresh() {
    if (!this._hass || this.busy) return;
    this.busy = true;
    this.render();
    try {
      this.entries = await this._hass.callWS({type:"irpat_efficiency/overview"});
      this.error = false;
    } catch (err) {
      this.entries = [];
      this.error = true;
    } finally {
      this.loaded = true;
      this.busy = false;
      this.render();
    }
  }

  t(ro, en) { return (this._hass?.language || "").startsWith("ro") ? ro : en; }

  node(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  }

  card(title, value) {
    const e = this.node("div", undefined, "card metric");
    e.append(this.node("div", title, "muted"), this.node("strong", value));
    return e;
  }

  render() {
    const root = this.shadowRoot;
    root.replaceChildren();
    const style = this.node("style");
    style.textContent = `
      :host{display:block;color:var(--primary-text-color);background:var(--primary-background-color);min-height:100%}
      main{padding:20px;max-width:1200px;margin:auto;box-sizing:border-box}
      header{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
      h1{font-size:1.5rem;flex:1;margin:0}h2{font-size:1.2rem}h3{font-size:1rem}
      .muted{color:var(--secondary-text-color)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:10px}
      .card{border:1px solid var(--divider-color);background:var(--card-background-color);border-radius:14px;padding:14px;margin-bottom:12px;box-sizing:border-box}
      .metric strong{font-size:1.7rem;display:block;margin-top:5px}
      button,a.action{background:var(--primary-color);color:var(--text-primary-color,#fff);border:0;border-radius:8px;padding:10px 14px;font:inherit;cursor:pointer;text-decoration:none}
      button:disabled{opacity:.6;cursor:default}button:focus-visible,a:focus-visible{outline:3px solid var(--primary-text-color)}
      .loops{overflow-x:auto;display:flex;gap:8px;padding:10px 4px 6px}
      .loop{flex:0 0 105px;min-width:0;text-align:center}
      .meter{width:20px;height:54px;border:2px solid #8796a5;border-radius:5px;margin:5px auto;background:repeating-linear-gradient(to bottom,transparent 0 8px,#8796a5 8px 9px)}
      .supply,.return{height:8px;border-radius:4px}.supply{background:#e57345}.return{background:#2196d3}
      .pipe{height:18px;width:4px;background:#8796a5;margin:auto}
      .label{overflow-wrap:anywhere}.room{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--divider-color)}
      @media(max-width:600px){main{padding:12px}}
    `;
    root.append(style);
    const main = this.node("main");
    const header = this.node("header");
    header.append(this.node("h1","irPaT & Eficiență"));
    const refresh = this.node("button",this.t("Actualizează","Refresh"));
    refresh.disabled = this.busy;
    refresh.addEventListener("click",()=>this.refresh());
    header.append(refresh);
    main.append(header);
    main.append(this.node("p",this.t("Prezentare generală · versiune experimentală","Overview · experimental version"),"muted"));
    const link = this.node("a",this.t("Configurează integrarea","Configure integration"),"action");
    link.href = "/config/integrations";
    main.append(link);
    if (this.busy) main.append(this.node("p",this.t("Se încarcă…","Loading…")));
    if (this.error) main.append(this.node("p",this.t("Nu s-a putut încărca configurația. Încearcă din nou.","Could not load configuration. Try again.")));
    if (!this.busy && !this.error && !this.entries.length) main.append(this.node("p",this.t("Nu există o configurație activă.","No active configuration.")));
    for (const entry of this.entries) {
      const t = entry.topology;
      main.append(this.node("h2",entry.name));
      const grid = this.node("div",undefined,"grid");
      for (const [key,ro,en] of [["floors","Niveluri","Floors"],["rooms","Încăperi","Rooms"],["manifolds","Distribuitoare","Manifolds"],["circuits","Circuite","Circuits"],["zones","Zone","Zones"],["sources","Surse","Sources"]])
        grid.append(this.card(this.t(ro,en),(t[key]||[]).length));
      main.append(grid);
      const rooms = new Map((t.rooms||[]).map(r=>[r.id,r]));
      for (const floor of t.floors||[]) {
        const section = this.node("section",undefined,"card");
        section.append(this.node("h2",floor.name));
        for (const room of (t.rooms||[]).filter(r=>r.floor_id===floor.id)) {
          const row = this.node("div",undefined,"room");
          const target = room.heating_target_c;
          row.append(this.node("span",room.name,"label"),this.node("span",target==null?"—":this.t("Țintă ","Target ")+target+" °C"));
          section.append(row);
        }
        for (const manifold of (t.manifolds||[]).filter(m=>m.floor_id===floor.id)) {
          section.append(this.node("h3",manifold.name));
          const loops = this.node("div",undefined,"loops");
          const circuits = (t.circuits||[]).filter(c=>c.manifold_id===manifold.id).sort((a,b)=>a.position-b.position);
          for (const circuit of circuits) {
            const loop = this.node("div",undefined,"loop");
            const label = this.node("strong",String(circuit.position));
            const meter = this.node("div",undefined,"meter");
            meter.setAttribute("aria-label",this.t("Debit neînregistrat","Flow not recorded"));
            loop.append(label,meter,this.node("div",undefined,"supply"),this.node("div",undefined,"pipe"),this.node("div",undefined,"return"),this.node("div",circuit.name,"label"),this.node("small",rooms.get(circuit.room_id)?.name||this.t("Neasociat","Unassigned"),"muted"),this.node("div","— l/min","muted"));
            loops.append(loop);
          }
          if (!circuits.length) section.append(this.node("p",this.t("Nu există circuite adăugate.","No circuits added."),"muted"));
          section.append(loops);
        }
        main.append(section);
      }
    }
    main.append(this.node("p",this.t("Debitele și temperaturile măsurate nu sunt încă disponibile în acest panou. Nu se transmit comenzi instalației.","Measured flows and temperatures are not yet available in this panel. No commands are sent to equipment."),"muted"));
    root.append(main);
  }
}

if (!customElements.get("irpat-efficiency-panel")) customElements.define("irpat-efficiency-panel",IrpatEfficiencyPanel);
